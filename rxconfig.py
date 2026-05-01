import reflex as rx
from dotenv import load_dotenv

load_dotenv("cardanoism/.env", override=True)

config = rx.Config(
    app_name="cardanoism",
    api_url="http://0.0.0.0:8000",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ],
    # Phase 3: トランザクション構築用に Lucid Evolution を導入。
    # libsodium-wrappers-sumo の事前バンドリング問題を回避するため、
    # JS 側では `await import(...)` の動的 import で読み込む (wallet_module.js)。
    frontend_packages=[
        "@lucid-evolution/lucid@^0.4.27",
    ],
    show_built_with_reflex=False,
)