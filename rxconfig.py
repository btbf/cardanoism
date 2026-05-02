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
    show_built_with_reflex=False,
)
