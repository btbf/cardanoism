"""Styles for the app."""

import reflex as rx

border_radius = "0.375rem"
border = f"1px solid {rx.color('gray', 6)}"
text_color = rx.color("gray", 11)
accent_text_color = rx.color("accent", 10)
accent_color = rx.color("accent", 1)
hover_accent_color = {"_hover": {"color": accent_text_color}}
hover_accent_bg = {"_hover": {"background_color": accent_color}}
content_width_vw = "90vw"
sidebar_width = "20em"

template_page_style = {
    "padding_top": ["6em","6em","6em","5.5em","5.5em"], 
    "margin_x":"auto", 
    "padding_x": ["auto","auto","auto","5em", "5em"], 
    "flex": "1", 
    "max-width": "1380px", 
    "font_family": "Noto Sans JP",
    
    "width":"100%",
    "display":"flex",
    "flex_wrap":"wrap",
    "spacing":"6",
    "padding":"2em 1em",
}

template_content_style = {
    "border_radius": border_radius,
    "padding_top": "1.2em",
    "margin_bottom": "2em",
    "min_height": "85vh",
    "font_family": "Noto Sans JP",
}

link_style = {
    "color": accent_text_color,
    "text_decoration": "none",
    **hover_accent_color,
}

overlapping_button_style = {
    "background_color": "white",
    "border_radius": border_radius,
}

markdown_style = {
    "code": lambda text: rx.code(text, color_scheme="gray"),
    "codeblock": lambda text, **props: rx.code_block(text, **props, margin_y="1em"),
    "a": lambda text, **props: rx.link(
        text,
        **props,
        font_weight="bold",
        text_decoration="underline",
        text_decoration_color=accent_text_color,
    ),
}

section_style = {
    "padding_left":"20px",
    "padding_right":"20px",
    "margin":"10px",
}


top_button = {
    "position": "fixed",
    "bottom": "100px",
    "right": "20px",
    "z-index": "100",
    #"background_color": "#007BFF",
    "color": "white",
    "border": "none",
    "padding": "10px 20px",
    #"border_radius": "5px",
    "cursor": "pointer",
    "display": "none",
}

# #top-button:hover {
#     background-color: #0056b3;
# }