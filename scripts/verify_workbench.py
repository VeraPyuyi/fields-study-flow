"""Exercise shipped file:// reports, not the development server."""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

from playwright.sync_api import sync_playwright

VIEWPORTS = [(1440, 900), (1280, 800), (390, 844), (768, 1024)]


def verify(root: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    result = {"pages": [], "interactions": {}, "human_learning_effectiveness": "not_measured"}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for width, height in VIEWPORTS:
            for name in ("paper_map.html", "paper_lens.html", "roadmap.html"):
                context = browser.new_context(viewport={"width": width, "height": height})
                context.route("http://**/*", lambda route: route.abort())
                context.route("https://**/*", lambda route: route.abort())
                page = context.new_page()
                errors, requests = [], []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: requests.append(request.url) if request.url.startswith(("http:", "https:")) else None)
                started = time.perf_counter()
                page.goto((root / name).resolve().as_uri())
                page.locator(".workbench").wait_for()
                page.wait_for_timeout(450)
                dimensions = page.evaluate("""() => ({width:innerWidth,scroll:document.documentElement.scrollWidth,
                  height:innerHeight, header:document.querySelector('.workbench-header').getBoundingClientRect().height,
                  center:document.querySelector('.center-surface').getBoundingClientRect().height})""")
                row = {"file": name, "viewport": [width, height], "errors": errors, "external_requests": len(requests), **dimensions}
                row["ready_ms"] = round((time.perf_counter() - started) * 1000)
                if name == "paper_map.html":
                    page.locator(".react-flow__edge-path").first.wait_for(state="attached")
                    page.wait_for_timeout(200)
                    row["visible_edges"] = page.locator(".react-flow__edge-path").evaluate_all("nodes=>nodes.filter(n=>{const r=n.getBoundingClientRect();return r.width>0||r.height>0}).length")
                    assert row["visible_edges"] >= 6, row
                    row["visible_nodes"] = page.locator(".react-flow__node:visible").count()
                    row["node_overflow"] = page.locator(".map-node").evaluate_all("nodes => nodes.filter(n=>n.scrollWidth>n.clientWidth+2).length")
                    row["transform"] = page.locator(".react-flow__viewport").get_attribute("style")
                    if width >= 1280:
                        row["geometry"] = page.locator(".react-flow__node:visible").evaluate_all("""nodes => {
                          const boxes=nodes.map(n=>n.getBoundingClientRect()); let overlaps=0;
                          for(let i=0;i<boxes.length;i++) for(let j=i+1;j<boxes.length;j++) {
                            const a=boxes[i],b=boxes[j]; if(a.left<b.right-1&&a.right>b.left+1&&a.top<b.bottom-1&&a.bottom>b.top+1) overlaps++;
                          }
                          const scale=new DOMMatrix(getComputedStyle(document.querySelector('.react-flow__viewport')).transform).a;
                          return {overlaps,minimum_label_px:Math.min(...nodes.map(n=>parseFloat(getComputedStyle(n.querySelector('.node-title')).fontSize)*scale))};
                        }""")
                        assert row["geometry"]["overlaps"] == 0, row
                        assert row["geometry"]["minimum_label_px"] >= 13, row
                page.screenshot(path=str(output / f"{name[:-5]}-{width}x{height}.png"))
                result["pages"].append(row)
                assert not errors, row
                assert not requests, row
                assert dimensions["scroll"] <= width + 1, row
                context.close()
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.goto((root / "paper_map.html").resolve().as_uri())
        page.locator(".react-flow__node:visible").first.wait_for()
        page.wait_for_timeout(400)
        node = page.locator(".react-flow__node:visible").nth(1)
        node.click()
        assert page.locator(".react-flow__node.selected").count() >= 1
        box = node.bounding_box()
        page.mouse.move(box["x"] + 35, box["y"] + 42)
        page.mouse.down()
        page.mouse.move(box["x"] + 85, box["y"] + 72, steps=12)
        page.mouse.up()
        moved = node.bounding_box()
        assert abs(moved["x"] - box["x"]) > 20
        node_id = node.get_attribute("data-id")
        toggle = page.locator(".map-node button[aria-expanded]").first
        if toggle.count():
            for _ in range(20):
                toggle.click()
                page.wait_for_timeout(50)
                expanded_count = page.locator(".react-flow__node:visible").count()
                toggle.click()
                page.wait_for_timeout(50)
                assert abs(page.locator(f'.react-flow__node[data-id="{node_id}"]').bounding_box()["x"] - moved["x"]) < 1
            result["interactions"]["branch_expansion"] = expanded_count
        page.reload()
        page.locator(f'.react-flow__node[data-id="{node_id}"]').wait_for()
        page.wait_for_timeout(400)
        restored = page.locator(f'.react-flow__node[data-id="{node_id}"]').bounding_box()
        assert abs(restored["x"] - moved["x"]) < 3
        result["interactions"]["drag_and_reload"] = "pass"
        context.close()
        blocked = browser.new_context(viewport={"width": 1280, "height": 800})
        blocked.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw new Error('blocked storage')}})")
        page = blocked.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto((root / "paper_lens.html").resolve().as_uri())
        page.locator(".workbench").wait_for()
        assert not errors
        result["interactions"]["storage_disabled"] = "pass"
        blocked.close()
        no_js = browser.new_context(java_script_enabled=False)
        page = no_js.new_page()
        page.goto((root / "paper_lens.html").resolve().as_uri())
        assert page.locator(".static-report-card article").count() > 0
        result["interactions"]["javascript_disabled"] = "readable"
        no_js.close()
        links = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
        links.route("http://**/*", lambda route: route.abort())
        links.route("https://**/*", lambda route: route.abort())
        page = links.new_page()
        page.goto((root / "paper_lens.html").resolve().as_uri())
        page.locator(".paragraph-select").first.click()
        page.get_by_role("tab", name="记录", exact=True).click()
        answer = page.locator(".record-editor textarea").first
        answer.fill("Browser verification note; not a mastery assessment.")
        with page.expect_download() as event:
            page.get_by_role("button", name="导出学习记录", exact=True).click()
        download = event.value
        saved = output / "test-study-state.json"
        download.save_as(saved)
        answer.fill("")
        page.locator(".header-tools input[type=file]").set_input_files(saved)
        page.wait_for_timeout(200)
        assert answer.input_value() == "Browser verification note; not a mastery assessment."
        result["interactions"]["record_export_import"] = "pass"
        graph_link = page.locator(".reading-graph-link")
        if graph_link.count():
            href = graph_link.get_attribute("href")
            graph_link.click()
            page.locator(".workbench").wait_for()
            target = unquote(urlsplit(href).fragment)
            page.locator(f'.react-flow__node[data-id="{target}"].selected').wait_for()
            result["interactions"]["paragraph_to_graph"] = "pass"
        links.close()
        snapshot = json.loads((root / "roadmap.json").read_text(encoding="utf-8"))
        local_hrefs = set()
        def collect(value):
            if isinstance(value, dict):
                if value.get("local_href"):
                    local_hrefs.add(value["local_href"])
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)
        collect(snapshot)
        for href in local_hrefs:
            parsed = urlsplit(href)
            assert not parsed.scheme and not parsed.netloc, href
            assert (root / unquote(parsed.path)).is_file(), href
        result["interactions"]["local_files_present"] = len(local_hrefs)
        html = (root / "paper_map.html").read_text(encoding="utf-8")
        payload_match = re.search(r'(<script type="application/json" id="fields-study-flow-data">)(.*?)(</script>)', html, re.S)
        if payload_match:
            payload = json.loads(payload_match[2])
            graph = payload["roadmap"]["paper_map"]
            parent = next(n["id"] for n in graph["nodes"] if n.get("kind") == "methodology")
            for index in range(100):
                node_id = f"benchmark-resource-{index}"
                graph["nodes"].append({"id": node_id, "kind": "resource", "role": "branch", "label": f"测试资料 {index}", "plain_explanation": "Synthetic UI benchmark; not research evidence."})
                graph["edges"].append({"id": f"benchmark-edge-{index}", "from": parent, "to": node_id, "label": "supports"})
            encoded = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
            benchmark_file = output / "benchmark-100-nodes.html"
            benchmark_file.write_text(html[:payload_match.start(2)] + encoded + html[payload_match.end(2):], encoding="utf-8")
            benchmark = browser.new_context(viewport={"width": 1440, "height": 900})
            page = benchmark.new_page()
            started = time.perf_counter()
            page.goto(benchmark_file.resolve().as_uri())
            parent_node = page.locator(f'.react-flow__node[data-id="{parent}"]')
            parent_node.wait_for()
            parent_node.locator("button[aria-expanded]").click()
            page.wait_for_function("document.querySelectorAll('.react-flow__node').length >= 108")
            result["interactions"]["synthetic_100_branches"] = {"rendered_nodes": page.locator(".react-flow__node").count(), "ready_ms": round((time.perf_counter() - started) * 1000), "scientific_evidence": False}
            benchmark.close()
        browser.close()
    (output / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.report_dir, args.output), ensure_ascii=False, indent=2))
