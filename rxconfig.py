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
    # Reflex 0.9 で auto setter がデフォルト OFF になったため一時 ON。
    # 将来的に削除されるので、各 State に setter を明示定義する作業は別途必要。
    state_auto_setters=True,
    show_built_with_reflex=False,
)
