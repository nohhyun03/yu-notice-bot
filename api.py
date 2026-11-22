import asyncio

from aiohttp import web

import db
from auth import verify_init_data

INIT_DATA_HEADER = "X-Telegram-Init-Data"


def make_app(bot_token, categories):
    async def current_user(request):
        user = verify_init_data(request.headers.get(INIT_DATA_HEADER, ""), bot_token)
        if user is None:
            raise web.HTTPUnauthorized(text='{"error": "unauthorized"}', content_type="application/json")
        return str(user["id"]), user.get("first_name", "")

    async def get_categories(request):
        return web.json_response([{"key": k, "name": v["name"]} for k, v in categories.items()])

    async def get_subscriptions(request):
        chat_id, _ = await current_user(request)
        return web.json_response({"subscriptions": await asyncio.to_thread(db.get_subscriptions, chat_id)})

    async def put_subscriptions(request):
        chat_id, name = await current_user(request)
        try:
            body = await request.json()
        except ValueError:
            raise web.HTTPBadRequest(text="invalid JSON")
        selected = body.get("subscriptions") if isinstance(body, dict) else None
        if not isinstance(selected, list) or not all(isinstance(c, str) and c in categories for c in selected):
            raise web.HTTPBadRequest(text="subscriptions must be a list of known category keys")
        await asyncio.to_thread(db.set_subscriptions, chat_id, name, list(dict.fromkeys(selected)))
        return web.json_response({"subscriptions": selected})

    async def get_bookmarks(request):
        chat_id, _ = await current_user(request)
        return web.json_response(await asyncio.to_thread(db.list_bookmarks, chat_id))

    async def delete_bookmark(request):
        chat_id, _ = await current_user(request)
        bookmark_id = db.parse_id(request.match_info["id"])
        if bookmark_id is None or not await asyncio.to_thread(db.delete_bookmark, chat_id, bookmark_id):
            raise web.HTTPNotFound()
        return web.Response(status=204)

    app = web.Application()
    app.router.add_get("/api/categories", get_categories)
    app.router.add_get("/api/subscriptions", get_subscriptions)
    app.router.add_put("/api/subscriptions", put_subscriptions)
    app.router.add_get("/api/bookmarks", get_bookmarks)
    app.router.add_delete("/api/bookmarks/{id}", delete_bookmark)
    return app
