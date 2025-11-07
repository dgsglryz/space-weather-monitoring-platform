from channels.generic.websocket import AsyncJsonWebsocketConsumer

class UpdateConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        self.group = f'user_{user.id}' if (user and user.is_authenticated) else 'public'
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group, self.channel_name)

    async def weather_update(self, event):
        await self.send_json(event['data'])
