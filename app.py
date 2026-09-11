import re
import time
from datetime import datetime
from urllib.parse import (
    parse_qsl,
    urlencode,
    urljoin,
    urlparse,
    urlunparse,
)

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup


DEFAULT_URL = (
    "https://www.carrefour.es/electronica/"
    "television-65-a-75-pulgadas/F-1031Z1y0sj/c"
)

MARCAS = [
    "Samsung",
    "LG",
    "TCL",
    "Hisense",
    "Philips",
    "Sony",
    "Haier",
    "Xiaomi",
    "Panasonic",
    "Sharp",
    "Toshiba",
    "JVC",
    "Thomson",
    "Grundig",
    "Daewoo",
]

PATRON_PRECIO = re.compile(
    r"(?<!\d)(\d{1,4}(?:[. ]\d{3})*(?:,\d{1,2})?)\s*€"
)


def limpiar_texto(texto):
    """Elimina espacios y saltos de línea innecesarios."""
    return re.sub(r"\s+", " ", texto or "").strip()


def validar_url_carrefour(url):
    """Comprueba que la URL pertenece a carrefour.es."""
    try:
        url_analizada = urlparse(url.strip())

        return (
            url_analizada.scheme in {"http", "https"}
            and url_analizada.netloc.lower().endswith("carrefour.es")
        )

    except Exception:
        return False


def crear_url_pagina(url, numero_pagina):
    """Añade el número de página a la URL de la categoría."""
    url_analizada = urlparse(url)

    parametros = dict(
        parse_qsl(
            url_analizada.query,
            keep_blank_values=True,
        )
    )

    if numero_pagina > 1:
        parametros["page"] = str(numero_pagina)
    else:
        parametros.pop("page", None)

    nueva_consulta = urlencode(parametros)

    return urlunparse(
        url_analizada._replace(
            query=nueva_consulta
        )
    )


def identificar_marca(nombre_producto):
    """Identifica la marca dentro del nombre del producto."""
    nombre_limpio = limpiar_texto(nombre_producto)

    for marca in sorted(
        MARCAS,
        key=len,
        reverse=True,
    ):
        coincidencia = re.search(
            rf"\b{re.escape(marca)}\b",
            nombre_limpio,
            re.IGNORECASE,
        )

        if coincidencia:
            return marca

    return "No identificada"


def identificar_modelo(nombre_producto, marca):
    """Intenta extraer el código de modelo del nombre del producto."""
    nombre_limpio = limpiar_texto(nombre_producto)

    if marca == "No identificada":
        return nombre_limpio

    coincidencia_marca = re.search(
        rf"\b{re.escape(marca)}\b",
        nombre_limpio,
        re.IGNORECASE,
    )

    if not coincidencia_marca:
        return nombre_limpio

    texto_despues_marca = nombre_limpio[
        coincidencia_marca.end():
    ].strip(" -–,|")

    patron_modelo = re.compile(
        r"\b(?=[A-Z0-9.-]*\d)"
        r"[A-Z0-9][A-Z0-9.-]{3,}\b",
        re.IGNORECASE,
    )

    modelo_encontrado = patron_modelo.search(
        texto_despues_marca
    )

    if modelo_encontrado:
        return modelo_encontrado.group(0)

    if texto_despues_marca:
        return texto_despues_marca

    return nombre_limpio


def convertir_precio_a_numero(precio_texto):
    """Convierte un precio español a un número decimal."""
    if not precio_texto:
        return None

    precio_limpio = (
        precio_texto
        .replace("€", "")
        .replace(" ", "")
        .replace(".", "")
        .replace(",", ".")
    )

    try:
        return float(precio_limpio)

    except ValueError:
        return None


def encontrar_tarjeta_producto(enlace):
    """Busca el contenedor HTML que incluye título, precio y vendedor."""
    elemento = enlace

    for _ in range(10):
        elemento = getattr(
            elemento,
            "parent",
            None,
        )

        if elemento is None:
            break

        texto_elemento = limpiar_texto(
            elemento.get_text(
                " ",
                strip=True,
            )
        )

        enlaces_producto = elemento.select(
            'a[href*="/p"]'
        )

        if (
            "€" in texto_elemento
            and len(texto_elemento) < 3500
            and len(enlaces_producto) <= 4
        ):
            return elemento

    return enlace.parent


def obtener_vendedor(texto_tarjeta):
    """Extrae el comercio indicado después de 'Vendido por'."""
    patrones_vendedor = [
        r"Vendido\s+por\s+(.+?)(?=Click&Collect)",
        r"Vendido\s+por\s+(.+?)(?=Envío\s+gratis)",
        r"Vendido\s+por\s+(.+?)(?=Envio\s+gratis)",
        r"Vendido\s+por\s+(.+?)(?=Envío\s+Gratis)",
        r"Vendido\s+por\s+(.+?)(?=Super\s+Precio)",
        r"Vendido\s+por\s+(.+?)(?=Oferta\s+Carrefour)",
        r"Vendido\s+por\s+(.+?)(?=Más\s+ofertas)",
        r"Vendido\s+por\s+(.+?)(?=Ver\s+detalle)",
        r"Vendido\s+por\s+(.+?)(?=Añadir)",
        r"Vendido\s+por\s+(.+)$",
    ]

    for patron in patrones_vendedor:
        coincidencia = re.search(
            patron,
            texto_tarjeta,
            re.IGNORECASE,
        )

        if coincidencia:
            vendedor = limpiar_texto(
                coincidencia.group(1)
            )

            if vendedor and len(vendedor) <= 100:
                return vendedor

    return "No indicado"


def obtener_titulo_producto(enlace):
    """Obtiene el nombre del producto desde el enlace."""
    titulo = limpiar_texto(
        enlace.get_text(
            " ",
            strip=True,
        )
    )

    if len(titulo) >= 8:
        return titulo

    titulo = limpiar_texto(
        enlace.get("title")
        or enlace.get("aria-label")
        or ""
    )

    return titulo


def analizar_html(html, url_base):
    """Analiza el HTML y devuelve los productos identificados."""
    soup = BeautifulSoup(
        html,
        "lxml",
    )

    productos = []
    urls_detectadas = set()

    enlaces = soup.select(
        'a[href*="/p"]'
    )

    for enlace in enlaces:
        href = enlace.get("href", "")

        if not href:
            continue

        url_producto = urljoin(
            url_base,
            href,
        ).split("#")[0]

        ruta_producto = urlparse(
            url_producto
        ).path

        if "/p" not in ruta_producto:
            continue

        if url_producto in urls_detectadas:
            continue

        titulo_producto = obtener_titulo_producto(
            enlace
        )

        if len(titulo_producto) < 8:
            continue

        tarjeta = encontrar_tarjeta_producto(
            enlace
        )

        if tarjeta is None:
            continue

        texto_tarjeta = limpiar_texto(
            tarjeta.get_text(
                " ",
                strip=True,
            )
        )

        precios_encontrados = PATRON_PRECIO.findall(
            texto_tarjeta
        )

        if not precios_encontrados:
            continue

        precio_actual_texto = precios_encontrados[-1]

        precio_actual = convertir_precio_a_numero(
            precio_actual_texto
        )

        vendedor = obtener_vendedor(
            texto_tarjeta
        )

        marca = identificar_marca(
            titulo_producto
        )

        modelo = identificar_modelo(
            titulo_producto,
            marca,
        )

        urls_detectadas.add(
            url_producto
        )

        productos.append(
            {
                "Marca": marca,
                "Modelo": modelo,
                "Producto": titulo_producto,
                "URL": url_producto,
                "Vendido por": vendedor,
                "Precio (€)": precio_actual,
            }
        )

    return productos


def descargar_html(sesion, url):
    """Descarga el HTML de una página."""
    respuesta = sesion.get(
        url,
        timeout=30,
    )

    respuesta.raise_for_status()

    return respuesta.text


@st.cache_data(
    ttl=900,
    show_spinner=False,
)
def recoger_productos(
    url_categoria,
    maximo_paginas,
    pausa_segundos,
):
    """Recorre las páginas del listado y construye la tabla."""
    sesion = requests.Session()

    sesion.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            ),
            "Accept-Language": (
                "es-ES,es;q=0.9,en;q=0.7"
            ),
            "Accept": (
                "text/html,"
                "application/xhtml+xml,"
                "application/xml;q=0.9,"
                "*/*;q=0.8"
            ),
            "Referer": "https://www.carrefour.es/",
        }
    )

    todos_los_productos = []
    urls_guardadas = set()
    avisos = []

    for numero_pagina in range(
        1,
        maximo_paginas + 1,
    ):
        url_pagina = crear_url_pagina(
            url_categoria,
            numero_pagina,
        )

        try:
            html = descargar_html(
                sesion,
                url_pagina,
            )

            productos_pagina = analizar_html(
                html,
                url_pagina,
            )

        except requests.RequestException as error:
            avisos.append(
                "No se pudo consultar la página "
                f"{numero_pagina}: {error}"
            )
            break

        productos_nuevos = []

        for producto in productos_pagina:
            if producto["URL"] not in urls_guardadas:
                productos_nuevos.append(
                    producto
                )

        if not productos_nuevos:
            if numero_pagina == 1:
                avisos.append(
                    "No se han detectado productos. "
                    "Carrefour puede haber cambiado "
                    "la estructura de la página o "
                    "bloqueado la petición."
                )

            break

        for producto in productos_nuevos:
            urls_guardadas.add(
                producto["URL"]
            )

            todos_los_productos.append(
                producto
            )

        if numero_pagina < maximo_paginas:
            time.sleep(
                pausa_segundos
            )

    for posicion, producto in enumerate(
        todos_los_productos,
        start=1,
    ):
        producto["Posición"] = posicion

    columnas = [
        "Posición",
        "Marca",
        "Modelo",
        "Producto",
        "URL",
        "Vendido por",
        "Precio (€)",
    ]

    dataframe = pd.DataFrame(
        todos_los_productos,
        columns=columnas,
    )

    return dataframe, avisos


st.set_page_config(
    page_title="Monitor Carrefour",
    page_icon="📺",
    layout="wide",
)

st.title("Monitor de posiciones Carrefour")

st.caption(
    "Consulta la posición, marca, modelo, "
    "vendedor, precio y URL de los productos."
)


with st.sidebar:
    st.header("Configuración")

    url_categoria = st.text_input(
        "URL de la categoría",
        value=DEFAULT_URL,
    )

    maximo_paginas = st.number_input(
        "Máximo de páginas",
        min_value=1,
        max_value=20,
        value=5,
        step=1,
    )

    pausa_segundos = st.slider(
        "Pausa entre páginas",
        min_value=0.5,
        max_value=5.0,
        value=1.5,
        step=0.5,
    )

    ejecutar = st.button(
        "Recoger productos",
        type="primary",
        use_container_width=True,
    )

    st.info(
        "La posición corresponde al orden "
        "observado en el listado durante "
        "la consulta."
    )


if ejecutar:
    if not validar_url_carrefour(
        url_categoria
    ):
        st.error(
            "Introduce una URL válida "
            "del dominio carrefour.es."
        )

        st.stop()

    with st.spinner(
        "Analizando el listado..."
    ):
        datos, avisos = recoger_productos(
            url_categoria.strip(),
            int(maximo_paginas),
            float(pausa_segundos),
        )

    for aviso in avisos:
        st.warning(
            aviso
        )

    if datos.empty:
        st.error(
            "No se han podido recoger productos."
        )

    else:
        st.success(
            f"Se han recogido {len(datos)} productos."
        )

        columna_1, columna_2, columna_3 = st.columns(
            3
        )

        columna_1.metric(
            "Productos",
            len(datos),
        )

        columna_2.metric(
            "Marcas",
            int(
                datos["Marca"].nunique()
            ),
        )

        if datos["Precio (€)"].notna().any():
            precio_medio = datos[
                "Precio (€)"
            ].mean()

            columna_3.metric(
                "Precio medio",
                f"{precio_medio:.2f} €",
            )

        else:
            columna_3.metric(
                "Precio medio",
                "N/D",
            )

        st.dataframe(
            datos,
            use_container_width=True,
            hide_index=True,
            column_config={
                "URL": st.column_config.LinkColumn(
                    "URL",
                    display_text="Abrir producto",
                ),
                "Precio (€)": (
                    st.column_config.NumberColumn(
                        "Precio (€)",
                        format="%.2f €",
                    )
                ),
            },
        )

        archivo_csv = datos.to_csv(
            index=False,
        ).encode(
            "utf-8-sig"
        )

        fecha_archivo = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        st.download_button(
            label="Descargar resultados en CSV",
            data=archivo_csv,
            file_name=(
                "carrefour_productos_"
                f"{fecha_archivo}.csv"
            ),
            mime="text/csv",
        )

        st.caption(
            "Los productos repetidos se eliminan "
            "por URL y se conserva su primera posición."
        )

else:
    st.write(
        "Pulsa **Recoger productos** "
        "para analizar el listado."
    )
