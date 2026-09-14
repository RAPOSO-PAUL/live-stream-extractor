import json
import re
import sys
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright


# ============================================================
# CONFIGURAÇÃO
# ============================================================

if len(sys.argv) < 2:
    print("Uso:")
    print("python extractor.py https://exemplo.com/canal")
    sys.exit(1)

SOURCE_URL = sys.argv[1]

results = {}

NETWORK_LOG = "network.log"


# ============================================================
# LOG
# ============================================================

def log(message):
    print(message, flush=True)

    with open(
        NETWORK_LOG,
        "a",
        encoding="utf-8"
    ) as f:
        f.write(message + "\n")


# ============================================================
# URL
# ============================================================

def normalize_url(url, base_url=None):

    if not url:
        return None

    url = str(url).strip()

    url = url.strip("\"'")

    if base_url:
        url = urljoin(
            base_url,
            url
        )

    try:
        parsed = urlparse(url)

        if parsed.scheme not in (
            "http",
            "https"
        ):
            return None

        return url

    except Exception:
        return None


# ============================================================
# CLASSIFICAÇÃO
# ============================================================

def classify(url, content_type=""):

    value = (
        url + " " + content_type
    ).lower()

    if (
        ".m3u8" in value
        or "mpegurl" in value
    ):
        return "hls"

    if (
        ".mpd" in value
        or "dash+xml" in value
    ):
        return "dash"

    if ".m3u" in value:
        return "m3u"

    if ".mp4" in value:
        return "mp4"

    if ".ts" in value:
        return "mpeg-ts"

    if (
        "/file.txt" in value
        or value.endswith("file.txt")
    ):
        return "file-txt"

    return "other"


# ============================================================
# SALVAR STREAM
# ============================================================

def add_stream(
    url,
    content_type="",
    stream_type=None,
    source="network"
):

    url = normalize_url(url)

    if not url:
        return

    if not stream_type:
        stream_type = classify(
            url,
            content_type
        )

    if url not in results:

        results[url] = {
            "url": url,
            "type": stream_type,
            "content_type": content_type,
            "source": source,
            "host": urlparse(url).netloc
        }

        log(
            f"[STREAM] [{stream_type}] {url}"
        )


# ============================================================
# PLAYLIST HLS
# ============================================================

def is_hls(text):

    if not text:
        return False

    text = text[:100000]

    return (
        "#EXTM3U" in text
        or "#EXT-X-" in text
    )


# ============================================================
# DASH
# ============================================================

def is_dash(text):

    if not text:
        return False

    text = text[:100000].lower()

    return (
        "<mpd" in text
        or "<mpd " in text
        or "urn:mpeg:dash" in text
    )


# ============================================================
# EXTRAIR URLS
# ============================================================

def extract_urls(text):

    if not text:
        return set()

    patterns = [

        # HLS
        r'https?://[^"\'<>\s]+\.m3u8(?:\?[^"\'<>\s]*)?',

        # M3U
        r'https?://[^"\'<>\s]+\.m3u(?:\?[^"\'<>\s]*)?',

        # DASH
        r'https?://[^"\'<>\s]+\.mpd(?:\?[^"\'<>\s]*)?',

        # file.txt
        r'https?://[^"\'<>\s]+/file\.txt(?:\?[^"\'<>\s]*)?',

        # MP4
        r'https?://[^"\'<>\s]+\.mp4(?:\?[^"\'<>\s]*)?',

        # TS
        r'https?://[^"\'<>\s]+\.ts(?:\?[^"\'<>\s]*)?',
    ]

    found = set()

    for pattern in patterns:

        for match in re.findall(
            pattern,
            text,
            re.IGNORECASE
        ):

            url = normalize_url(match)

            if url:
                found.add(url)

    return found


# ============================================================
# ANALISAR RESPOSTA
# ============================================================

def inspect_response(
    url,
    content_type="",
    body=None
):

    if not url:
        return

    url = normalize_url(url)

    if not url:
        return

    lower_url = url.lower()
    lower_type = (
        content_type or ""
    ).lower()


    # --------------------------------------------------------
    # HLS MIME
    # --------------------------------------------------------

    if (
        "mpegurl" in lower_type
        or "application/vnd.apple.mpegurl"
        in lower_type
    ):

        add_stream(
            url,
            content_type,
            "hls",
            "network"
        )


    # --------------------------------------------------------
    # DASH MIME
    # --------------------------------------------------------

    if "dash+xml" in lower_type:

        add_stream(
            url,
            content_type,
            "dash",
            "network"
        )


    # --------------------------------------------------------
    # M3U8
    # --------------------------------------------------------

    if ".m3u8" in lower_url:

        add_stream(
            url,
            content_type,
            "hls",
            "network"
        )


    # --------------------------------------------------------
    # MPD
    # --------------------------------------------------------

    if ".mpd" in lower_url:

        add_stream(
            url,
            content_type,
            "dash",
            "network"
        )


    # --------------------------------------------------------
    # FILE.TXT
    # --------------------------------------------------------

    if (
        lower_url.endswith("/file.txt")
        or "/file.txt?" in lower_url
    ):

        if body and is_hls(body):

            add_stream(
                url,
                content_type,
                "hls-file-txt",
                "network"
            )

        else:

            log(
                f"[TXT] {url}"
            )


    # --------------------------------------------------------
    # Playlist pelo conteúdo
    # --------------------------------------------------------

    if body:

        if is_hls(body):

            add_stream(
                url,
                content_type,
                "hls",
                "content"
            )

        elif is_dash(body):

            add_stream(
                url,
                content_type,
                "dash",
                "content"
            )


        # URLs dentro da resposta
        for found in extract_urls(body):

            add_stream(
                found,
                "",
                classify(found),
                "embedded"
            )


# ============================================================
# MAIN
# ============================================================

def main():

    # Limpa log anterior
    open(
        NETWORK_LOG,
        "w",
        encoding="utf-8"
    ).close()

    log(
        "=========================================="
    )

    log(
        "       LIVE STREAM EXTRACTOR"
    )

    log(
        "=========================================="
    )

    log(
        f"[+] URL: {SOURCE_URL}"
    )


    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        context = browser.new_context(

            user_agent=(
                "Mozilla/5.0 "
                "(X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131.0 Safari/537.36"
            ),

            viewport={
                "width": 1920,
                "height": 1080
            },

            ignore_https_errors=True
        )


        page = context.new_page()


        # ====================================================
        # REQUEST
        # ====================================================

        def on_request(request):

            try:

                url = request.url

                lower = url.lower()

                # Loga somente URLs potencialmente relevantes
                if (
                    ".m3u8" in lower
                    or ".m3u" in lower
                    or ".mpd" in lower
                    or "file.txt" in lower
                    or "manifest" in lower
                    or "playlist" in lower
                ):

                    log(
                        f"[REQUEST] {url}"
                    )

                    add_stream(
                        url,
                        "",
                        classify(url),
                        "request"
                    )

            except Exception as error:

                log(
                    f"[REQUEST ERROR] {error}"
                )


        page.on(
            "request",
            on_request
        )


        # ====================================================
        # RESPONSE
        # ====================================================

        def on_response(response):

            try:

                url = response.url

                headers = response.headers

                content_type = (
                    headers.get(
                        "content-type",
                        ""
                    )
                )

                lower_url = url.lower()

                lower_type = (
                    content_type.lower()
                )


                interesting = (

                    ".m3u8" in lower_url

                    or ".mpd" in lower_url

                    or ".m3u" in lower_url

                    or "file.txt"
                    in lower_url

                    or "mpegurl"
                    in lower_type

                    or "dash+xml"
                    in lower_type

                    or "manifest"
                    in lower_url

                    or "playlist"
                    in lower_url

                    or "json"
                    in lower_type
                )


                if interesting:

                    log(
                        f"[RESPONSE] "
                        f"{response.status} "
                        f"{content_type} "
                        f"{url}"
                    )


                body = None


                # Ler somente respostas textuais
                if interesting:

                    try:

                        body = response.text()

                    except Exception:
                        body = None


                inspect_response(
                    url,
                    content_type,
                    body
                )


            except Exception as error:

                log(
                    f"[RESPONSE ERROR] {error}"
                )


        page.on(
            "response",
            on_response
        )


        # ====================================================
        # ABRIR PÁGINA
        # ====================================================

        log(
            "[+] Abrindo página..."
        )

        try:

            page.goto(
                SOURCE_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )

            log(
                f"[+] Página carregada: {page.url}"
            )

        except Exception as error:

            log(
                f"[!] Erro ao abrir página: {error}"
            )


        # ====================================================
        # PRIMEIRA ESPERA
        # ====================================================

        log(
            "[+] Aguardando carregamento do player..."
        )

        page.wait_for_timeout(
            10000
        )


        # ====================================================
        # TENTAR DAR PLAY EM ELEMENTOS HTML5
        # ====================================================

        try:

            videos = page.locator(
                "video"
            )

            count = videos.count()

            log(
                f"[+] Elementos video encontrados: {count}"
            )

            for i in range(count):

                try:

                    videos.nth(i).scroll_into_view_if_needed()

                    videos.nth(i).evaluate(
                        """
                        video => {
                            video.muted = true;
                            video.play().catch(() => {});
                        }
                        """
                    )

                except Exception:
                    pass

        except Exception as error:

            log(
                f"[!] Erro ao iniciar vídeo: {error}"
            )


        # ====================================================
        # SEGUNDA ESPERA
        # ====================================================

        log(
            "[+] Aguardando requisições do player..."
        )

        page.wait_for_timeout(
            30000
        )


        # ====================================================
        # SALVAR SCREENSHOT
        # ====================================================

        try:

            page.screenshot(
                path="player.png",
                full_page=True
            )

            log(
                "[+] Screenshot salvo."
            )

        except Exception as error:

            log(
                f"[!] Screenshot falhou: {error}"
            )


        # ====================================================
        # SALVAR HTML
        # ====================================================

        try:

            html = page.content()

            with open(
                "page.html",
                "w",
                encoding="utf-8"
            ) as f:

                f.write(html)

            log(
                "[+] HTML salvo."
            )


            # Procurar URLs no HTML

            for found in extract_urls(
                html
            ):

                add_stream(
                    found,
                    "",
                    classify(found),
                    "html"
                )

        except Exception as error:

            log(
                f"[!] Erro salvando HTML: {error}"
            )


        # ====================================================
        # ELEMENTOS DE MÍDIA
        # ====================================================

        try:

            elements = page.locator(
                "video, audio, source"
            ).all()

            log(
                f"[+] Elementos de mídia: {len(elements)}"
            )

            for element in elements:

                for attribute in (
                    "src",
                    "data-src",
                    "data-url",
                    "data-file",
                    "data-video",
                    "data-stream"
                ):

                    try:

                        value = (
                            element.get_attribute(
                                attribute
                            )
                        )

                        if value:

                            absolute = normalize_url(
                                value,
                                page.url
                            )

                            if absolute:

                                add_stream(
                                    absolute,
                                    "",
                                    classify(
                                        absolute
                                    ),
                                    "media-element"
                                )

                    except Exception:
                        pass

        except Exception as error:

            log(
                f"[!] Erro nos elementos de mídia: {error}"
            )


        browser.close()


    # ========================================================
    # RESULTADO FINAL
    # ========================================================

    output = {

        "source": SOURCE_URL,

        "count": len(results),

        "streams": list(
            results.values()
        )
    }


    with open(
        "streams.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False
        )


    log("")
    log(
        "=========================================="
    )

    log(
        f"STREAMS ENCONTRADOS: {len(results)}"
    )

    log(
        "=========================================="
    )


    for stream in results.values():

        log(
            f"[{stream['type']}] "
            f"{stream['url']}"
        )


if __name__ == "__main__":
    main()
