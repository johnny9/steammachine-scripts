#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps


PUBLIC_API = "https://www.steamgriddb.com/api/public"
GAME_PAGE = "https://www.steamgriddb.com/game/{game_id}"


def get_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "accept": "application/json, text/plain, */*",
            "referer": "https://www.steamgriddb.com/",
            "user-agent": "codex-steam-shortcut-skill/1.1",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict, referer: str) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "accept": "application/json, text/plain, */*",
            "origin": "https://www.steamgriddb.com",
            "referer": referer,
            "user-agent": "codex-steam-shortcut-skill/1.1",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"user-agent": "codex-steam-shortcut-skill/1.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def pick_game(query: str) -> tuple[int, str, str]:
    url = f"{PUBLIC_API}/search/autocomplete?term={urllib.parse.quote(query)}"
    payload = get_json(url)
    if not payload.get("success") or not payload.get("data"):
        raise SystemExit(f"No SteamGridDB game match for query: {query}")
    first = payload["data"][0]
    game_id = int(first["id"])
    name = first.get("name") or query
    print(f"steamgrid_game={name} ({game_id})")
    return game_id, name, GAME_PAGE.format(game_id=game_id)


def search_assets(game_id: int, asset_type: str, dimensions: list[str] | None, limit: int = 96) -> list[dict]:
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
        "limit": limit,
        "user_steam64": None,
        "user_steam64_likes": None,
    }
    data = post_json(f"{PUBLIC_API}/search/assets", payload, GAME_PAGE.format(game_id=game_id))
    if not data.get("success"):
        raise RuntimeError(data)
    assets = data["data"].get("assets") or []
    return [
        asset
        for asset in assets
        if asset.get("url")
        and not asset.get("nsfw")
        and not asset.get("epilepsy")
        and not asset.get("humor")
        and not asset.get("is_animated")
    ]


def rank(asset: dict, preferred_dims: set[tuple[int, int]]) -> tuple[int, int, int, int]:
    dims = (int(asset.get("width") or 0), int(asset.get("height") or 0))
    return (
        1 if dims in preferred_dims else 0,
        int(asset.get("hearts") or 0),
        int(asset.get("downloads") or 0),
        int(asset.get("date") or 0),
    )


def pick_asset(game_id: int, asset_type: str, preferred_dims: list[tuple[int, int]], dimensions: list[str] | None) -> dict | None:
    assets = search_assets(game_id, asset_type, dimensions)
    if not assets:
        return None
    return max(assets, key=lambda asset: rank(asset, set(preferred_dims)))


def save_image(raw: bytes, dest: Path, size: tuple[int, int], contain: bool = False) -> None:
    image = Image.open(BytesIO(raw)).convert("RGBA")
    if contain:
        image.thumbnail(size, Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", size, (0, 0, 0, 0))
        canvas.alpha_composite(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
        image = canvas
    else:
        image = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
    image.save(dest)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True, help="Game name to search on SteamGridDB")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--game-id", type=int, default=None)
    parser.add_argument("--api-key", default="", help="Accepted for compatibility; public SteamGridDB endpoints are used by default")
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    if args.game_id is None:
        game_id, game_name, provider_url = pick_game(args.query)
    else:
        game_id, game_name, provider_url = args.game_id, args.query, GAME_PAGE.format(game_id=args.game_id)
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
        asset = pick_asset(game_id, asset_type, preferred, dimensions)
        if not asset:
            missing.append(name)
            continue
        raw = download(asset["url"])
        save_image(raw, out / filename, size, contain)
        if name == "hero":
            save_image(raw, out / "hero.png", (1920, 620), False)
        sources["assets"][name] = {
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
        print(out / filename)

    (out / "sources.json").write_text(json.dumps(sources, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if missing and not args.allow_partial:
        raise SystemExit(f"Missing SteamGridDB asset types: {', '.join(missing)}")
    if not sources["assets"]:
        raise SystemExit("No SteamGridDB artwork was downloaded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
