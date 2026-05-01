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
    # Phase 1+2 のウォレット接続は raw CIP-30 + 自前 bech32 実装で完結 (npm 依存ゼロ)。
    # Phase 3 (トランザクション構築) で Lucid Evolution / MeshSDK のいずれかを導入予定。
    show_built_with_reflex=False,
)