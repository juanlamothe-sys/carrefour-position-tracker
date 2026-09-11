import re
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse

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

PRICE_RE = re.compile(
    r"(?<!\d)(\d{1,4}(?:[. ]\d{3})*(?:,\d{1,2})?)\s*€"
)


def limpiar_texto(texto):
    return re.sub(r"\s+", " ", texto or "").strip()


def validar_url(url):
    try:
        parsed = urlparse(url.strip())

        return (
            parsed.scheme in {"http", "https"}
            and parsed.netloc.lower().endswith("carrefour.es")
        )

    except Exception:
        return False


def url_pagina(url, pagina):
    parsed = urlparse(url)

    parametros = dict(
        parse_qsl(
            parsed.query,
            keep_blank_values=True,
        )
    )

    if pagina > 1:
        parametros["page"] = str(pagina)
    else:
        parametros.pop("page", None)

    return urlunparse(
        parsed._replace(
            query=urlencode(parametros)
        )
    )


def identificar_marca_modelo(nombre_producto):
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
            texto_posterior = nombre_limpio[
                coincidencia.end():
            ].strip(" -–,|")

            modelo_encontrado = re.search(
                r"\b(?=[A-Z0-9.-]*\d)"
                r"(?:[A-Z0-9]*A-Z0-9.-]{3,})\b",
               *texto_posterior,
                re.IGNORECASE,
            )

      *     if modelo_encontrado:
       *        modelo = modelo_encontrado*group(0)
            else:
       *        modelo = texto_posterior

*           return marca, modelo

 *  return "No identificada", nombre*limpio


def convertir_precio(prec*o):
    if not precio:
        ret*rn None

    precio_limpio = (
   *    precio.replace("€", "")
      * .replace(" ", "")
        .replac*(".", "")
        .replace(",", ".*)
    )

    try:
        return f*oat(precio_limpio)

    except ValueError:
        return None


def buscar_tarjeta_producto(enlace):
    elemento = enlace

    for _ in range(10):
        elemento = getattr(
            elemento,
            "parent",
            None,
        )

        if elemento is None:
            break

        texto = limpiar_texto(
            elemento.get_text(
                " ",
                strip=True,
            )
        )

        enlaces_producto = elemento.select(
            'a[href*="/p"]'
        )

        if (
            "€" in texto
            and len(texto) < 3000
            and len(enlaces_producto) <= 4
        ):
            return elemento

    return enlace.parent


def obtener_vendedor(texto_tarjeta):
    patrones = [
        r"Vendido por\s+(.+?)(?:Click&Collect)",
        r"Vendido por\s+(.+?)(?:Envío gratis)",
        r"Vendido por\s+(.+?)(?:Envio gratis)",
        r"Vendido por\s+(.+?)(?:Envío Gratis)",
        r"Vendido por\s+(.+?)(?:Añadir)",
        r"Vendido por\s+(.+?)(?:Ver detalle)",
        r"Vendido por\s+(.+?)$",
    ]

    for patron in patrones:
        coincidencia = re.search(
            patron,
            texto_tarjeta,
            re.IGNORECASE,
        )

        if coincidencia:
            vendedor = limpiar_texto(
                coincidencia.group(1)
            )

            if len(vendedor) < 100:
                return vendedor

    return "No indicado"


def analizar_html(html, url_base):
    soup = BeautifulSoup(
        html,
        "lxml",
    )

    resultados = []
    urls_detectadas = set()

    enlaces = soup.select(
        'a[href*="/p"]'
    )

    for enlace*in enlaces:
        href = enlace.*et("href", "")

        url_produc*o = urljoin(
            url_base,*            href,
        ).split(*#")[0]

        if not url_product*:
            continue

        if*url_producto in urls_detectadas:
 *          continue

        if "/p* not in urlparse(
            url_*roducto
        ).path:
          * continue

        nombre_producto*= limpiar_texto(
            enlac*.get_text(
                " ",
  *             strip=True,
         *  )
        )

        if len(nomb*e_producto) < 8:
            nombr*_producto = limpiar_texto(
       *        enlace.get("title")
      *         or enlace.get("aria-label*)
                or ""
          * )

        if len(nombre_producto* < 8:
            continue

      * tarjeta = buscar_tarjeta_producto*
            enlace
        )

   *    if tarjeta is None:
          * continue

        texto_tarjeta =*limpiar_texto(
            tarjeta*get_text(
                " ",
   *            strip=True,
          * )
        )

        precios = PR*CE_RE.findall(
            texto_t*rjeta
        )

        if not pr*cios:
            continue

      * # Si aparecen precio anterior y a*tual,
        # normalmente el últ*mo es el precio vigente.
        p*ecio_actual = precios[-1]

       *vendedor = obtener_vendedor(
     *      texto_tarjeta
        )

   *    marca, modelo = identificar_ma*ca_modelo(
            nombre_prod*cto
        )

        urls_detect*das.add(
            url_producto
*       )

        resultados.appen*(
            {
                "M*rca": marca,
                "Mode*o": modelo,
                "Produ*to": nombre_producto,
            *   "URL": url_producto,
          *     "Vendido por": vendedor,
    *           "Precio (€)": convertir*precio(
                    precio*actual
                ),
        *   }
        )

    return resulta*os


def descargar_pagina(sesion, *rl):
    respuesta = sesion.get(
 *      url,
        timeout=30,
    )

    respuesta.raise_for_status()

    return respuesta.text


@st.cache_data(
    ttl=900,
    show_spinner=False,
)
def recoger_productos(
    url,
    maximo_paginas,
    pausa,
):
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
            "Referer": (
                "https://www.carrefour.es/"
            ),
        }
    )

    todos_productos = []
    urls_guardadas = set()
    avisos = []

    for pagina in range(
        1,
        maximo_paginas + 1,
    ):
        direccion_pagina = url_pagina(
            url,
            pagina,
        )

        try:
            html = descargar_pagina(
                sesion,
                direccion_pagina,
            )

            productos_pagina = analizar_html(
                html,
                direccion_pagina,
            )

        except requests.RequestException as error:
            avisos.append(
                f"Error en la página {pagina}: {error}"
            )
            break

        productos_nuevos = [
            producto
            for producto in productos_pagina
            if producto["URL"] not in urls_guardadas
        ]

        if not productos_nuevos:
            if pagina == 1:
                avisos.append(
                    "No se han detectado productos. "
                    "Carrefour puede haber cambiado "
                    "su página o bloqueado la petición."
                )

            break

        for producto in productos_nuevos:
            urls_guardadas.add(
                producto["URL"]
            )

            todos_productos.append(
                producto
            )

        if pagina < maximo_paginas:
            time.sleep(pausa)

    for posicion, producto in enumerate(
        todos_productos,
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
        todos_productos,
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
    "Consulta la posición, marca, modelo, precio "
    "y vendedor de los productos de una categoría."
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

    pausa = st.slider(
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
        "observado en el momento de la consulta."
    )


if ejecutar:
    if not validar_url(url_categoria):
        st.error(
            "Introduce una URL válida de carrefour.es."
        )

        st.stop()

    with st.spinner(
        "Analizando el listado de Carrefour..."
    ):
        datos, avisos = recoger_productos(
            url_categoria.strip(),
            int(maximo_paginas),
            float(pausa),
        )

    for aviso in avisos:
        st.warning(aviso)

    if datos.empty:
        st.error(
            "No se han podido recoger productos."
        )

    else:
        st.success(
            f"Se han recogido {len(datos)} productos."
        )

        columna_1, columna_2, columna_3 = (
            st.columns(3)
        )

        columna_1.metric(
            "Productos",
            len(datos),
        )

        columna_2.metric(
            "Marcas",
            datos["Marca"].nunique(),
        )

        if datos["Precio (€)"].notna().any():
            precio_medio = datos[
                "Precio (€)"
            ].mean()

            columna_3.metric(
                "Precio medio",
                f"{precio_medio:,.2f} €",
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
        ).encode("utf-8-sig")

        fecha = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        st.download_button(
            label="Descargar resultados en CSV",
            data=archivo_csv,
            file_name=(
                f"carrefour_productos_{fecha}.csv"
            ),
            mime="text/csv",
        )

        st.caption(
            "Los productos repetidos se eliminan "
            "por URL conservando su primera posición."
        )

else:
    st.write(
        "Pulsa **Recoger productos** para "
        "analizar el listado."
    )
