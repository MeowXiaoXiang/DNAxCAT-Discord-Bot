import discord
from discord.ext import commands

class Common(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="website", description="九藏喵窩官方網站")
    async def dnaxcat_website(self, interaction: discord.Interaction):
        await interaction.response.send_message("https://www.dnaxcat.net/", ephemeral=False)

    @discord.app_commands.command(name="forum", description="九藏喵窩論壇")
    async def dnaxcat_forum(self, interaction: discord.Interaction):
        await interaction.response.send_message("https://dnaxcattalk.dnaxcat.com.tw/forum.php", ephemeral=False)

    @discord.app_commands.command(name="youtube", description="九藏喵窩動畫 YouTube 頻道")
    async def dnaxcat_youtube(self, interaction: discord.Interaction):
        await interaction.response.send_message("https://www.youtube.com/@dnaxcat-king/", ephemeral=False)

    @discord.app_commands.command(name="wiki", description="九藏喵窩 Wiki")
    async def dnaxcat_wiki(self, interaction: discord.Interaction):
        await interaction.response.send_message("https://dnaxcat.fandom.com/zh-tw/wiki/", ephemeral=False)

async def setup(bot):
    await bot.add_cog(Common(bot))