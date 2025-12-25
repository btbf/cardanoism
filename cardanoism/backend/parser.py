from bs4 import BeautifulSoup
from typing import List, Dict, Any


def html_to_semantic_blocks(raw_html: str) -> List[Dict]:
    soup = BeautifulSoup(raw_html, "lxml")

    blocks: List[Dict[str, Any]] = []
    block_index = 0
    team_section = soup.select_one("section#team")
    if team_section:
        team_section.extract()

    def build_block(title: str | None, nodes: list[Any]) -> None:
        nonlocal block_index
        html = "".join(str(n) for n in nodes).strip()
        blocks.append(
            {
                "index": block_index,
                "type": "section" if title else "orphan",
                "semantic_title": title,
                "html": html,
            }
        )
        block_index += 1

    def add_section_block(section, title: str) -> None:
        section_html = str(section).strip()
        if not section_html:
            return
        build_block(title, [section_html])

    def next_section_nodes(h3_tag) -> list[Any]:
        nodes: list[Any] = []
        for sib in h3_tag.next_siblings:
            if getattr(sib, "name", None) == "h3":
                break
            if isinstance(sib, str) and not sib.strip():
                continue
            nodes.append(sib)
        if nodes:
            return nodes
        parent = h3_tag.parent
        if parent is None:
            return nodes
        for sib in parent.next_siblings:
            if getattr(sib, "name", None) == "h3":
                break
            if getattr(sib, "find", None) and sib.find("h3"):
                break
            if isinstance(sib, str) and not sib.strip():
                continue
            nodes.append(sib)
        return nodes

    h3_tags = soup.find_all("h3")
    if h3_tags:
        for h3_tag in h3_tags:
            title = h3_tag.get_text(strip=True)
            nodes = next_section_nodes(h3_tag)
            build_block(title, nodes)
        if team_section:
            add_section_block(team_section, "team")
        return blocks

    if raw_html.strip():
        build_block(None, [raw_html.strip()])
    return blocks
