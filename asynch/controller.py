import asyncio
import struct
from asynch.constants import sc_control_msg_type, sc_copy_key, sc_screen_power_mode
from asynch.constants.input import android_metastate, android_keyevent_action, android_motionevent_action, \
    android_motionevent_buttons


class Controller:
    def __init__(self, device_client):
        self.device = device_client

    async def empty_control_socket(self, interval=0.02, loop=10):
        for idx in range(loop):
            try:
                await asyncio.wait_for(self.device.control_socket.read(0x10000), timeout=interval)
            except:
                return

    async def inject(self, msg):
        async with self.device.device_lock:
            await self.device.control_socket.write(msg)

    async def inject_without_lock(self, msg):
        await self.device.control_socket.write(msg)

    async def inject_keycode(self, keycode, action=android_keyevent_action.AKEY_EVENT_ACTION_DOWN, repeat=0,
                       metastate=android_metastate.AMETA_NONE):
        """
        keycode: in constants.keycodes.py
        action: android_keyevent_action
        metastate: android_metastate
        inject_data: lens 14
        """
        msg_type = sc_control_msg_type.SC_CONTROL_MSG_TYPE_INJECT_KEYCODE
        inject_data = struct.pack(">BBiii", msg_type, action, keycode, repeat, metastate)
        await self.inject(inject_data)
        return inject_data

    async def inject_text(self, text):
        """
        inject_data: lens 5 + *
        """
        msg_type = sc_control_msg_type.SC_CONTROL_MSG_TYPE_INJECT_TEXT
        buffer = text.encode("utf-8")
        inject_data = struct.pack(">BI", msg_type, len(buffer)) + buffer
        await self.inject(inject_data)
        return inject_data

    async def inject_touch_event(self, x, y, resolution, action=android_motionevent_action.AMOTION_EVENT_ACTION_DOWN, touch_id=-1,
                                 pressure=1, buttons=android_motionevent_buttons.AMOTION_EVENT_BUTTON_PRIMARY):
        """
        action: android_motionevent_action
        touch_id: touch_id use to distinguish multi touch
        x: touch location x
        y: touch location y
        height: resolution height
        width: resolution width
        pressure: touch pressure. 0 or 1,1 is max
        action_button: android_motionevent_buttons, mouse key
        buttons: same as pressure 0 or 1
        inject_data: lens 32
        """
        if action == android_motionevent_action.AMOTION_EVENT_ACTION_UP:
            pressure = 0
        msg_type = sc_control_msg_type.SC_CONTROL_MSG_TYPE_INJECT_TOUCH_EVENT
        x, y = max(x, 0), max(y, 0)
        inject_data = struct.pack(">BBqiiHHHii", msg_type, action, touch_id, int(x), int(y),
                                  int(resolution[0]), int(resolution[1]), pressure, buttons, pressure)
        await self.inject(inject_data)
        return inject_data

    async def inject_scroll_event(self, x, y, distance_x, distance_y, resolution, buttons=android_motionevent_buttons.AMOTION_EVENT_BUTTON_PRIMARY):
        """
        buttons: android_motionevent_buttons
        inject_data: lens 21
        """
        msg_type = sc_control_msg_type.SC_CONTROL_MSG_TYPE_INJECT_SCROLL_EVENT
        x, y = max(x, 0), max(y, 0)
        inject_data = struct.pack(">BiiHHhhi", msg_type, int(x), int(y), int(resolution[0]),
                                  int(resolution[1]), int(distance_x)*6000, int(distance_y)*6000, buttons)
        await self.inject(inject_data)
        return inject_data

    async def back_or_screen_on(self, action=android_keyevent_action.AKEY_EVENT_ACTION_DOWN):
        """
        inject_data: lens 2
        """
        msg_type = sc_control_msg_type.SC_CONTROL_MSG_TYPE_BACK_OR_SCREEN_ON
        inject_data = struct.pack(">BB", msg_type, action)
        await self.inject(inject_data)
        return inject_data

    async def get_clipboard(self, copy_key=sc_copy_key.SC_COPY_KEY_COPY):
        """
        copy_key: none, copy, cut
        inject_data: lens 2
        """
        msg_type = sc_control_msg_type.SC_CONTROL_MSG_TYPE_GET_CLIPBOARD
        inject_data = struct.pack(">BB", msg_type, copy_key)
        async with self.device.device_lock:
            await self.empty_control_socket()
            await self.inject_without_lock(inject_data)
            try:
                # 剪切板为空时，此处为堵塞
                _meta = await asyncio.wait_for(self.device.control_socket.read_exactly(5), 1)
                msg_type, msg_lens = struct.unpack('>BI', _meta)
                return await self.device.control_socket.read_exactly(msg_lens)
            except Exception as e:
                print(f'no clipborad ! {e}')
                return b''

    async def set_clipboard(self, text, sequence=1, paste=True):
        """
        sequence: 序列号用于标识复制是否成功。不为0时，set_clipboard成功后scrcpy会返回这个sequence
        paste: if input widget is focus, auto paste
        inject_data: lens 10 + *
        """
        msg_type = sc_control_msg_type.SC_CONTROL_MSG_TYPE_SET_CLIPBOARD
        byte_data = text.encode("utf-8")
        inject_data = struct.pack(">BQ?I", msg_type, sequence, paste, len(byte_data)) + byte_data
        async with self.device.device_lock:
            await self.empty_control_socket()
            await self.inject_without_lock(inject_data)
            sequence = (await self.device.control_socket.read_exactly(9))[1:]
            return sequence

    async def set_screen_power_mode(self, screen_power_mode=sc_screen_power_mode.SC_SCREEN_POWER_MODE_NORMAL):
        """
        inject_data: lens 2
        """
        msg_type = sc_control_msg_type.SC_CONTROL_MSG_TYPE_SET_SCREEN_POWER_MODE
        inject_data = struct.pack(">BB", msg_type, screen_power_mode)
        await self.inject_without_lock(inject_data)
        return inject_data

    async def swipe(self, x, y, end_x, end_y, resolution, unit=5, delay=1):
        """
        swipe (x,y) to (end_x, end_y), 匀速移动，每unit个像素点出发一次touch move事件
        """
        x_1, y_1 = x, y
        end_x, end_y = min(end_x, resolution[0]), min(end_y, resolution[1])
        step = 1
        while True:
            if x_1 > end_x:
                x_1 -= min(x-end_x, unit)
            elif x_1 < end_x:
                x_1 += min(end_x-x_1, unit)
            if y_1 > end_y:
                y_1 -= min(y_1-end_y, unit)
            elif y < end_y:
                y_1 += min(end_y-y_1, unit)
            if x_1 == end_x and y_1 == end_y:
                break
            step += 1
        unit_delay = delay/step
        await self.inject_touch_event(x, y, resolution, android_motionevent_action.AMOTION_EVENT_ACTION_DOWN)
        while True:
            if x > end_x:
                x -= min(x-end_x, unit)
            elif x < end_x:
                x += min(end_x-x, unit)
            if y > end_y:
                y -= min(y-end_y, unit)
            elif y < end_y:
                y += min(end_y-y, unit)
            await self.inject_touch_event(x, y, resolution, android_motionevent_action.AMOTION_EVENT_ACTION_MOVE)
            await asyncio.sleep(unit_delay)
            if x == end_x and y == end_y:
                await self.inject_touch_event(x, y, resolution, android_motionevent_action.AMOTION_EVENT_ACTION_UP)
                break


if __name__ == "__main__":
    a = Controller('b')
    a.set_clipboard('23233121')
