#!/usr/bin/env python3
"""Fetch a complete static SteamGridDB artwork set for a game."""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from io import BytesIO
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ModuleNotFoundError as exc:
    raise SystemExit("Pillow is required: install the python3-pillow package") from exc


PUBLIC_API = "https://www.steamgriddb.com/api/public"
GAME_PAGE = "https://www.steamgriddb.com/game/{game_id}"
USER_AGENT = "codex-switch-steam-skill/1.0"


def request_json(url: str, payload: dict | None = None, referer: str = "https://www.steamgriddb.com/") -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": "https://www.steamgriddb.com",
            "referer": referer,
            "user-agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"user-agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def choose_game(query: str, game_id: int | None) -> tuple[int, str, str]:
    if game_id is not None:
        return game_id, query, GAME_PAGE.format(game_id=game_id)
    url = f"{PUBLIC_API}/search/autocomplete?term={urllib.parse.quote(query)}"
    payload = request_json(url)
    if not payload.get("success") or not payload.get("data"):
        raise SystemExit(f"No SteamGridDB game match for: {query}")
    selected = payload["data"][0]
    selected_id = int(selected["id"])
    return selected_id, selected.get("name") or query, GAME_PAGE.format(game_id=selected_id)


def search_assets(game_id: int, asset_type: str, dimensions: list[str] | None) -> list[dict]:
    game_page = GAME_PAGE.format(game_id=game_id)
    payload = {
        "styles": ["all"],
        "languages": ["all"],
        "dimensions": dimensions or ["all"],
        "formats": ["all"],
        "order": "score_desc",
        "game_id": [game_id],
        "static": True,
        "animated": False,
        "nsfw": False,
        "epilepsy": False,
        "humor": False,
        "untagged": True,
        "asset_type": asset_type,
        "page": 0,
        "limit": 96,
        "user_steam64": None,
        "user_steam64_likes": None,
    }
    response = request_json(f"{PUBLIC_API}/search/assets", payload, game_page)
    if not response.get("success"):
        raise RuntimeError(f"SteamGridDB asset search failed: {response}")
    return [
        asset
        for asset in response["data"].get("assets", [])
        if asset.get("url")
        and not asset.get("nsfw")
        and not asset.get("epilepsy")
        and not asset.get("humor")
        and not asset.get("is_animated")
    ]


def rank(asset: dict, preferred: set[tuple[int, int]]) -> tuple[int, int, int, int]:
    dimensions = (int(asset.get("width") or 0), int(asset.get("height") or 0))
    return (
        1 if dimensions in preferred else 0,
        int(asset.get("hearts") or 0),
        int(asset.get("downloads") or 0),
        int(asset.get("date") or 0),
    )


def select_asset(game_id: int, asset_type: str, preferred: list[tuple[int, int]], dimensions: list[str] | None) -> dict | None:
    assets = search_assets(game_id, asset_type, dimensions)
    return max(assets, key=lambda asset: rank(asset, set(preferred))) if assets else None


def save_image(raw: bytes, destination: Path, size: tuple[int, int], contain: bool) -> None:
    image = Image.open(BytesIO(raw)).convert("RGBA")
    if contain:
        image.thumbnail(size, Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", size, (0, 0, 0, 0))
        canvas.alpha_composite(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
        image = canvas
    else:
        image = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
    image.save(destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--game-id", type=int, default=None)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()

    output = Path(args.output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    game_id, game_name, provider_url = choose_game(args.query, args.game_id)
    print(f"steamgrid_game={game_name} ({game_id})")

    specs = {
        "poster": ("grid", [(600, 900)], ["600x900"], "poster.png", (600, 900), False),
        "capsule": ("grid", [(920, 430), (460, 215)], ["920x430", "460x215"], "capsule.png", (920, 430), False),
        "hero": ("hero", [(3840, 1240), (1920, 620)], ["3840x1240", "1920x620"], "library_hero.png", (3840, 1240), False),
        "logo": ("logo", [(650, 248), (1280, 720)], None, "logo.png", (1280, 720), True),
        "icon": ("icon", [(512, 512), (256, 256), (128, 128)], None, "icon.png", (512, 512), True),
    }
    sources: dict[str, object] = {
        "provider": "SteamGridDB",
        "provider_url": provider_url,
        "game_id": game_id,
        "game": game_name,
        "assets": {},
    }
    missing: list[str] = []
    for name, (asset_type, preferred, dimensions, filename, size, contain) in specs.items():
        asset = select_asset(game_id, asset_type, preferred, dimensions)
        if asset is None:
            missing.append(name)
            continue
        raw = download(asset["url"])
        save_image(raw, output / filename, size, contain)
        if name == "hero":
            save_image(raw, output / "hero.png", (1920, 620), False)
        sources["assets"][name] = {  # type: ignore[index]
            "asset_type": asset_type,
            "id": asset["id"],
            "file": filename,
            "source_url": asset["url"],
            "asset_page": f"https://www.steamgriddb.com/{asset_type}/{asset['id']}",
            "author": (asset.get("author") or {}).get("name"),
            "width": asset.get("width"),
            "height": asset.get("height"),
            "hearts": asset.get("hearts"),
            "downloads": asset.get("downloads"),
        }
        print(output / filename)

    (output / "sources.json").write_text(json.dumps(sources, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if missing and not args.allow_partial:
        raise SystemExit(f"Missing SteamGridDB artwork types: {', '.join(missing)}")
    if not sources["assets"]:
        raise SystemExit("No SteamGridDB artwork was downloaded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
