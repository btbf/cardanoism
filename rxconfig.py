import reflex as rx
from dotenv import load_dotenv

# シークレットは Infisical CLI (`infisical run -- ...`) で注入する。
# .env が残っている場合は fallback としてのみ読み込む (Infisical 値を上書きしない)。
load_dotenv("cardanoism/.env", override=False)

config = rx.Config(
    app_name="cardanoism",
    api_url="http://0.0.0.0:8000",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ],
    show_built_with_reflex=False,
)
