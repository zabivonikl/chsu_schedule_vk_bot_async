from json import dumps

from Keyboards.keyboard import Keyboard


class VkKeyboard(Keyboard):
    def __init__(self) -> None:
        super().__init__()
        self._line_count = 0
        self._keyboard = None

    def _clear(self) -> None:
        self._line_count = 0
        self._keyboard = {
            "one_time": False,
            "buttons": [],
            "inline": False
        }

    def _add_line(self) -> None:
        self._keyboard['buttons'].append([])
        self._line_count += 1

    def _add_button(self, text: str, color: str = "primary") -> None:
        self._keyboard['buttons'][self._line_count - 1].append({
            "action": {
                "type": "text",
                "label": text
            },
            "color": color
        })

    def _get_keyboard(self) -> str:
        return dumps(self._keyboard)
