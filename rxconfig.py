import reflex as rx

config = rx.Config(
    app_name="cardanoism",
    api_url="http://localhost:8000",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ],
)