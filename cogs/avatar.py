import discord
from discord.ext import commands
from typing import Optional, Union
import requests
from PIL import Image
from io import BytesIO

class Avatar(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="查看成員頭貼", description="顯示目標成員的頭貼，可擇一使用選擇用戶或輸入用戶id")
    @discord.app_commands.describe(
        member="選擇你想查看的成員",
        user_id="輸入用戶id"
    )
    @discord.app_commands.rename(member="成員", user_id="用戶id")
    async def avatar(self, interaction: discord.Interaction, member: Optional[Union[discord.Member, discord.User]] = None, user_id: Optional[str] = None):
        if not member and not user_id:
            member = interaction.user

        if member and user_id:
            await interaction.response.send_message(embed=discord.Embed(title="錯誤", description="請勿同時輸入成員和用戶id", color=0xff0000), ephemeral=True)
            return

        if user_id:
            try:
                user_id_int = int(user_id)
                user = self.bot.get_user(user_id_int)
                if user is None:
                    await interaction.response.send_message(embed=discord.Embed(
                        title="錯誤", 
                        description="無法找到指定的用戶", 
                        color=0xff0000
                        ), 
                        ephemeral=True
                    )
                    return
            except ValueError:
                await interaction.response.send_message(embed=discord.Embed(
                        title="錯誤",
                        description="請輸入正確的用戶id\n可透過打開discord設定內的開發者模式，使用滑鼠右鍵選單來對用戶複製id",
                        color=0xff0000
                    ),
                    ephemeral=True
                )
                return

        # 用 defer 延遲回應，讓 Discord 知道操作正在進行中
        await interaction.response.defer()

        if member:
            member = member
        elif user_id:
            member = user

        avatar_url = member.avatar.url
        response = requests.get(avatar_url)
        image = Image.open(BytesIO(response.content))
        image = image.convert("RGB")
        pixels = image.getdata()
        r_avg = 0
        g_avg = 0
        b_avg = 0
        for pixel in pixels:
            r, g, b = pixel
            r_avg += r
            g_avg += g
            b_avg += b
        num_pixels = image.size[0] * image.size[1]
        r_avg //= num_pixels
        g_avg //= num_pixels
        b_avg //= num_pixels
        avg_color = (r_avg, g_avg, b_avg)
        color = discord.Color.from_rgb(*avg_color)
        embed = discord.Embed(title=f"{member.name} 的頭貼", description=f"[ :link: [完整大圖連結]]({avatar_url})\n", color=color)
        embed.set_image(url=avatar_url)

        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Avatar(bot))