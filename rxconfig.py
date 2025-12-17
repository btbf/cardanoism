import reflex as rx

config = rx.Config(
    app_name="cardanoism",
    api_url="http://127.0.0.1:8000",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ],
)