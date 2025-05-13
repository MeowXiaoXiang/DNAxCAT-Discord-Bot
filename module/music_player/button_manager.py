from discord.ui import View, Button
from discord import ButtonStyle, Interaction
from loguru import logger

class MusicPlayerButtons(View):
    def __init__(self, button_handler_callback):
        """
        初始化音樂播放器按鈕 View
        :param button_handler_callback: 處理按鈕事件的 callback
        """
        super().__init__(timeout=None)
        self.button_handler_callback = button_handler_callback

        # ---- 按鈕設定 ----
        self.previous_button = Button(emoji="⏮️", style=ButtonStyle.grey, custom_id="previous", row=0)
        self.play_pause_button = Button(emoji="⏯️", style=ButtonStyle.blurple, custom_id="play_pause", row=0)
        self.next_button = Button(emoji="⏭️", style=ButtonStyle.grey, custom_id="next", row=0)
        self.loop_button = Button(emoji="🔄", style=ButtonStyle.grey, custom_id="loop", row=0)
        self.leave_button = Button(label="離開頻道", emoji="🚪", style=ButtonStyle.red, custom_id="leave", row=1)

        # ---- 添加按鈕到 view ----
        self.add_item(self.previous_button)
        self.add_item(self.play_pause_button)
        self.add_item(self.next_button)
        self.add_item(self.loop_button)
        self.add_item(self.leave_button)

        # ---- 綁定 callback ----
        self.previous_button.callback = self.button_callback
        self.play_pause_button.callback = self.button_callback
        self.next_button.callback = self.button_callback
        self.loop_button.callback = self.button_callback
        self.leave_button.callback = self.button_callback

    async def button_callback(self, interaction: Interaction):
        """
        處理所有音樂控制按鈕的 callback，並記錄操作
        """
        await interaction.response.defer()
        button_action = interaction.data.get("custom_id")
        if not button_action:
            logger.error("[MusicPlayerButtons] 按鈕回調中找不到 custom_id")
            return
        logger.info(f"[MusicPlayerButtons] 收到按鈕事件: {button_action}")
        if self.button_handler_callback:
            try:
                await self.button_handler_callback(interaction, button_action)
            except Exception as e:
                logger.exception(f"[MusicPlayerButtons] 處理按鈕 callback 時發生錯誤: {button_action}，{e}")
        else:
            logger.error("[MusicPlayerButtons] 未設置 button_handler_callback，無法處理按鈕事件")

    async def update_buttons(self, updates: dict):
        """
        批量更新按鈕屬性，並記錄更新內容
        :param updates: dict, 按鈕狀態更新資訊
        """
        if not isinstance(updates, dict):
            logger.error("[MusicPlayerButtons] 傳入的 updates 參數格式錯誤，應該是字典格式")
            raise ValueError("updates 必須是字典格式！")
        logger.debug(f"[MusicPlayerButtons] 更新按鈕狀態: {updates}")
        for child in self.children:
            if isinstance(child, Button) and child.custom_id in updates:
                update = updates[child.custom_id]
                if not isinstance(update, dict):
                    logger.error(f"[MusicPlayerButtons] 按鈕 {child.custom_id} 的更新數據格式錯誤：{update}")
                    raise ValueError(f"按鈕 {child.custom_id} 的更新數據必須是字典格式！")
                try:
                    if "label" in update and isinstance(update["label"], str):
                        child.label = update["label"]
                    if "emoji" in update and isinstance(update["emoji"], str):
                        child.emoji = update["emoji"]
                    if "style" in update and isinstance(update["style"], ButtonStyle):
                        child.style = update["style"]
                    if "disabled" in update and isinstance(update["disabled"], bool):
                        child.disabled = update["disabled"]
                except Exception as e:
                    logger.exception(f"[MusicPlayerButtons] 更新按鈕 {child.custom_id} 時發生錯誤: {e}")
                    raise ValueError(f"更新按鈕 {child.custom_id} 的過程中出現無效資訊！")

    async def remove_all_buttons(self):
        """
        移除所有按鈕，並記錄操作
        """
        logger.info("[MusicPlayerButtons] 正在移除所有按鈕...")
        self.clear_items()

class PaginationButtons(View):
    def __init__(self, button_handler_callback, timeout_callback=None, timeout_seconds=600):
        """
        初始化翻頁按鈕 View
        :param button_handler_callback: 處理按鈕事件的 callback
        :param timeout_callback: 超時回調函數
        :param timeout_seconds: 超時秒數
        """
        super().__init__(timeout=timeout_seconds)
        self.button_handler_callback = button_handler_callback
        self.timeout_callback = timeout_callback

        # ---- 按鈕設定 ----
        self.previous_button = Button(emoji="⬅️", style=ButtonStyle.grey, custom_id="previous_page", row=0)
        self.next_button = Button(emoji="➡️", style=ButtonStyle.grey, custom_id="next_page", row=0)

        # ---- 添加按鈕到 view ----
        self.add_item(self.previous_button)
        self.add_item(self.next_button)

        # ---- 綁定 callback ----
        self.previous_button.callback = self.button_callback
        self.next_button.callback = self.button_callback

    async def button_callback(self, interaction: Interaction):
        """
        處理所有翻頁按鈕的 callback，並記錄操作
        """
        await interaction.response.defer()
        button_action = interaction.data.get("custom_id")
        if not button_action:
            logger.error("[PaginationButtons] 按鈕回調中找不到 custom_id")
            return
        logger.info(f"[PaginationButtons] 收到按鈕事件: {button_action}")
        if self.button_handler_callback:
            try:
                await self.button_handler_callback(interaction, button_action)
            except Exception as e:
                logger.exception(f"[PaginationButtons] 處理按鈕 callback 時發生錯誤: {button_action}，{e}")
        else:
            logger.error("[PaginationButtons] 未設置 button_handler_callback，無法處理按鈕事件")

    async def on_timeout(self):
        """
        處理按鈕超時事件，並記錄操作
        """
        logger.info("[PaginationButtons] 已超時，正在清除按鈕...")
        if self.timeout_callback:
            try:
                await self.timeout_callback()
            except Exception as e:
                logger.exception(f"[PaginationButtons] 處理超時回調時發生錯誤：{e}")
        self.stop()

    async def update_buttons(self, updates: dict):
        """
        批量更新翻頁按鈕屬性，並記錄更新內容
        :param updates: dict, 按鈕狀態更新資訊
        """
        if not isinstance(updates, dict):
            logger.error("[PaginationButtons] 傳入的 updates 參數格式錯誤，應該是字典格式")
            raise ValueError("updates 必須是字典格式！")
        logger.debug(f"[PaginationButtons] 更新按鈕狀態: {updates}")
        for child in self.children:
            if isinstance(child, Button) and child.custom_id in updates:
                update = updates[child.custom_id]
                if not isinstance(update, dict):
                    logger.error(f"[PaginationButtons] 按鈕 {child.custom_id} 的更新數據格式錯誤：{update}")
                    raise ValueError(f"按鈕 {child.custom_id} 的更新數據必須是字典格式！")
                try:
                    if "label" in update and isinstance(update["label"], str):
                        child.label = update["label"]
                    if "emoji" in update and isinstance(update["emoji"], str):
                        child.emoji = update["emoji"]
                    if "style" in update and isinstance(update["style"], ButtonStyle):
                        child.style = update["style"]
                    if "disabled" in update and isinstance(update["disabled"], bool):
                        child.disabled = update["disabled"]
                except Exception as e:
                    logger.exception(f"[PaginationButtons] 更新按鈕 {child.custom_id} 時發生錯誤: {e}")
                    raise ValueError(f"更新按鈕 {child.custom_id} 的過程中出現無效資訊！")

    async def remove_all_buttons(self):
        """
        移除所有翻頁按鈕，並記錄操作
        """
        logger.info("[PaginationButtons] 正在移除所有按鈕...")
        self.clear_items()
