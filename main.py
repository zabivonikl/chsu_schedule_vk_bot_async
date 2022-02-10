import asyncio
import json
from datetime import datetime, timezone, timedelta

from aiohttp import web

import tokens
from APIs.Chsu.client import Chsu
from APIs.Telegram.client import Telegram
from APIs.Vk.client import Vk
from APIs.abstract_messanger import Messanger
from Handlers.Events.admins_message_event import AdminsMessageHandler
from Handlers.Events.another_event import AnotherEventHandler
from Handlers.Events.callback_event import CallbackHandler
from Handlers.Events.cancel_event import CancelHandler
from Handlers.Events.change_group_event import ChangeGroupHandler
from Handlers.schedule_change_checker import ScheduleChecker
from Wrappers.MongoDb.database import MongoDB
from Handlers.Events.event import EventHandler

routes = web.RouteTableDef()
event_loop = asyncio.get_event_loop()


def get_time(tz=3):
    return datetime.now(timezone(timedelta(hours=float(tz))))


@routes.get("/")
async def index(request):
    return web.Response(text=json.dumps({
        "Server": "working",
        "Server datetime:": get_time().strftime("%d.%m.%Y %H:%M:%S.%f"),
        "Server start datetime:": start_time.strftime("%d.%m.%Y %H:%M:%S.%f"),
        "Server uptime:": str(get_time() - start_time),
        f'CHSU API': f'{await chsu_api.get_status()}',
        f'Database': f'{await mongo_db_api.get_status()}',
        f'VK': f'{await vk_api.get_status()}',
        f'Telegram': {
            'is working': await telegram_api.get_status(),
            'is set webhook': await telegram_api.get_webhook() != ""
        },
        f'Mailing': 'working',
        f'Update checking': checker.get_status()
    }))


@routes.post('/vk/callback/{returnable}')
async def vk_event(request):
    data = await request.json()
    if data["type"] == "confirmation":
        return web.Response(text=request.match_info['returnable'])
    elif data["type"] == "message_event":
        event = {
            'from_id': data['object']['peer_id'],
            'payload': data['object']['payload']['address'],
            'time': get_time(),
            'event_id': data['object']["event_id"]
        }
    else:
        event = {
            'from_id': data['object']['message']['from_id'],
            'text': data['object']['message']['text'],
            'time': get_time()
        }
    if "X-Retry-Counter" not in request.headers:
        event_loop.create_task(EventHandler(vk_api, mongo_db_api, chsu_api).handle_event(event))
    return web.Response(text="ok")


@routes.post('/telegram/callback/fake')
async def telegram_event(request):
    return web.Response(text="ok")


@routes.get('/telegram/webhook/set/fake')
async def set_webhook(request):
    response = await telegram_api.set_webhook(
            f"https://{request.url.host}/telegram/callback/fake"
        )
    return web.Response(status=response['status'], text=response['text'])


@routes.post('/telegram/callback')
async def telegram_event(request):
    data = await request.json()
    try:
        if 'message' in data:
            event = {
                "from_id": data['message']['from']['id'],
                "text": data['message']['text'],
                'time': get_time()
            }
        elif 'callback_query' in data:
            event = {
                "from_id": data['callback_query']['from']['id'],
                "payload": data['callback_query']['data'],
                'time': get_time(),
                'event_id': data['callback_query']["id"]
            }
        else:
            event = None
        event_loop.create_task(EventHandler(telegram_api, mongo_db_api, chsu_api).handle_event(event))
        return web.Response(text="ok")
    except KeyError:
        return web.Response(text="ok")


@routes.get('/telegram/webhook/get')
async def get_webhook(request):
    return web.Response(text=await telegram_api.get_webhook())


@routes.get('/telegram/webhook/set')
async def set_webhook(request):
    response = await telegram_api.set_webhook(
            f"https://{request.url.host}/telegram/callback"
        )
    return web.Response(status=response['status'], text=response['text'])


@routes.get('/telegram/webhook/remove')
async def delete_webhook(request):
    await telegram_api.set_webhook()
    return web.Response(text='ok')


async def mailing():
    while get_time().second != 0:
        await asyncio.sleep(.5)
    print(f'Mailing started at: {get_time().strftime("%d.%m.%Y %H:%M:%S.%f")}')
    while True:
        users = await mongo_db_api.get_mailing_subscribers_by_time(get_time().strftime("%H:%M"))
        for user in users:
            event = {"from_id": user[0], "text": "Расписание на завтра", 'time': get_time()}
            if user[1] == telegram_api.get_name():
                await EventHandler(telegram_api, mongo_db_api, chsu_api).handle_event(event)
            elif user[1] == vk_api.get_name():
                await EventHandler(vk_api, mongo_db_api, chsu_api).handle_event(event)
        await asyncio.sleep(60)


def get_responsibility_chain(m: Messanger):
    admins_message = AdminsMessageHandler(m, mongo_db_api, chsu_api)
    another_event = AnotherEventHandler(m, mongo_db_api, chsu_api)
    callback_event = CallbackHandler(m, mongo_db_api, chsu_api)
    cancel_event = CancelHandler(m, mongo_db_api, chsu_api)
    change_group_event = ChangeGroupHandler(m, mongo_db_api, chsu_api)


if __name__ == "__main__":
    start_time = get_time()
    print(f"Start time: {start_time.strftime('%d.%m.%Y %H:%M:%S.%f')}")

    # init services
    print("Starting services...")
    chsu_api = Chsu(event_loop)
    mongo_db_api = MongoDB(tokens.MONGO_DB_LOGIN, tokens.MONGO_DB_PASSWORD, tokens.MONGO_DB_NAME)
    print("Done")

    # init messangers
    print("Starting messangers...")
    vk_api = Vk(tokens.VK_API, event_loop)
    telegram_api = Telegram(tokens.TELEGRAM_API, event_loop)
    print("Done")

    # init mailing
    print("Starting mailing...")
    event_loop.create_task(mailing())

    print("Starting schedule checker...")
    checker = ScheduleChecker(vk_api, telegram_api, mongo_db_api, chsu_api, event_loop, get_time)
    print("Done")

    # init server
    print("Starting web app...")
    app = web.Application()
    app.add_routes(routes)
    web.run_app(app, port=8080, host="127.0.0.1", loop=event_loop)
