from motor.motor_asyncio import AsyncIOMotorClient

from Wrappers.MongoDb.exceptions import EmptyResponse


class MongoDB:
    def __init__(self, db_login, db_password, db_name):
        self._client = AsyncIOMotorClient(
            f"mongodb+srv://{db_login}:{db_password}"
            f"@cluster.rfoam.mongodb.net/"
            f"{db_name}?"
            f"retryWrites=true&"
            f"w=majority",
            port=27017,
        )
        self._users_collection = self._client[db_name]["Users"]
        self._groups_collection = self._client[db_name]["Groups"]

    async def get_status(self):
        if (await self._users_collection.find_one({"id": 447828812}))["platform"] == 'vk':
            return "working"
        else:
            return "not working"

    async def get_user_data(self, platform_id, api_name, time=None):
        bot_user = await self._users_collection.find_one_and_update({
            "id": platform_id, "platform": api_name},
            {
                "$push": {"requests_time": {"$each": [time]}},
                "$unset": {"last_request_time": 1}
            }, upsert=True)
        if bot_user is None:
            raise EmptyResponse
        return {
            "group_name": bot_user["group_name"]
        } if "group_name" in bot_user and bot_user["group_name"] is not None else {
            "professor_name": bot_user["professor_name"]
        }

    async def set_user_data(self, user_id, api_name, group_name=None, professor_name=None):
        await self._users_collection.find_one_and_delete({"id": user_id, "platform": api_name})
        request = {"id": user_id, "platform": api_name}
        if group_name:
            request['group_name'] = group_name
        if professor_name:
            request['professor_name'] = professor_name
        await self._users_collection.insert_one(request)

    async def update_mailing_time(self, user_id, api_name, time=None):
        if time is None:
            update_parameter = {"$unset": {"mailing_time": 1}}
        else:
            update_parameter = {"$set": {"mailing_time": time}}
        await self._users_collection.update_one({
            "id": user_id,
            "platform": api_name,
        }, update_parameter)

    async def update_check_changes(self, user_id: int, api_name: str, check_changes=False) -> None:
        user_data = await self._users_collection.find_one({"id": user_id, "platform": api_name})
        request = {"users": {"id": user_data["id"], "platform": user_data["platform"]}}
        find_params = {"name": user_data['group_name'] if "group_name" in user_data else user_data['professor_name']}
        if check_changes:
            await self._groups_collection.update_one(find_params, {"$addToSet": request}, upsert=True)
        else:
            resp = await self._groups_collection.find_one_and_update(find_params, {"$pull": request}, upsert=True)
            if len(resp['users']) == 1:
                self._groups_collection.delete_one(find_params)

    async def update_schedule_hashes(self, hashes: list, group_name: str, is_daily_update: bool):
        group = await self._groups_collection.find_one({"name": group_name})
        old_hash_object = sorted(group['hashes'], key=lambda schedule_hash_object: schedule_hash_object['time'])
        return await self._get_difference_dates_and_update_hashes(old_hash_object, hashes, group_name, is_daily_update)

    async def _get_difference_dates_and_update_hashes(self, old_hashes, new_hashes, group_name, is_daily_update):
        different_hashes = self._get_difference(old_hashes, new_hashes)
        different_hash_objects = list(filter(lambda date_hash: date_hash['hash'] in different_hashes, new_hashes))
        for different_hash_object in different_hash_objects:
            await self._groups_collection.update_one(
                {"name": group_name, "hashes.time": different_hash_object['time']},
                {"$set": {"hashes.$.hash": different_hash_object['hash']}}
            )
        dates = list(map(lambda date_and_hash: date_and_hash['time'], different_hash_objects))\
            if not is_daily_update else []
        return list(map(lambda date: date.strftime("%d.%m.%Y"), dates))

    @staticmethod
    async def _get_difference(old_hashes, new_hashes):
        old_hashes_list = list(map(lambda date_and_hash: date_and_hash['hash'], old_hashes))
        new_hashes_list = list(map(lambda date_and_hash: date_and_hash['hash'], new_hashes))
        return list(set(new_hashes_list) - set(old_hashes_list))

    async def get_check_changes_members(self, group: str) -> list:
        group_members = []
        cursor = self._groups_collection.find({"name": group})
        while await cursor.fetch_next:
            user = cursor.next_object()
            group_members.append(user['users'])
        return group_members

    async def get_groups_list(self) -> list:
        group_names = []
        cursor = self._groups_collection.find()
        while await cursor.fetch_next:
            group = cursor.next_object()
            if "group_name" in group:
                group_names.append(group['group_name'])
            else:
                group_names.append(group['professor_name'])
        return group_names

    async def get_mailing_subscribers_by_time(self, time) -> list:
        simplified_subscribers = []
        cursor = self._users_collection.find({"mailing_time": time})
        while await cursor.fetch_next:
            subscriber = cursor.next_object()
            simplified_subscribers.append([subscriber["id"], subscriber["platform"]])
        return simplified_subscribers
