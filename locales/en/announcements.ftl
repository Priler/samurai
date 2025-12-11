# Announcements configuration
# 
# Format:
#   # Define reusable messages (can be referenced multiple times)
#   msg-name =
#       Message text here
#       Can be multiline
#
#   # Announcements - either inline or with @message reference
#   announcement-N =
#       @message: msg-name     (reference a message defined above)
#       @every: seconds        (interval between sends, can be defined as range ex. 1000-2000)
#       @groups: id1, id2      (optional: specific groups, omit for all)
#
#   # Or with inline message text
#   announcement-N =
#       Inline message text
#       @every: 3600


# ============================
# MESSAGE TEMPLATES (reusable)
# ============================

msg-report-reminder =
    ❕ Don't forget about the <b>!report</b> command which allows you to bring <u>rule violators</u> to the attention of the administration.
    
    <tg-spoiler><i>Spamming this command is punished with a permanent ban.</i></tg-spoiler>

msg-chat-rules =
    <b>📁 This is the chat of @howdyho_official channel</b>
    Be polite and follow the rules!
    
    📈 The chat has a <u>reputation system</u>
    ⛔️ Newbies cannot send media
    🤬 Profanity is <u>automatically deleted</u>
    👹 Off-topic/spam is punished with 🍌 bananas
    
    <b>Peace to all 🤞</b>

msg-donate =
    <b>🫰 Donate to the channel author:</b>
    
    <i>My Boosty:</i> https://boosty.to/howdyho
    <i>My Patreon:</i> <a href='https://www.patreon.com/user?u=22843414'>https://www.patreon.com/howdyho</a>
    <i>Our Discord:</i> <a href='https://discord.gg/6khaudi-kho-1123002520072097953'>https://discord.gg/howdyho</a>

msg-website =
    <b>😈 Did you know we have a website?</b>
    
    Here it is - https://howdyho.net
    We post top software, wallpapers, games, and lots of stuff for PC!
    
    <i>Come visit, you're always welcome!</i>

msg-share-bot =
    <b>🫰 Want your meme/post to be posted on the channel?</b>
    Click here - @hhsharebot


# ===============================
# ANNOUNCEMENTS (scheduled sends)
# ===============================

announcement-1 =
    @message: msg-report-reminder
    @every: 10000-20000

announcement-2 =
    @message: msg-chat-rules
    @every: 9600-12000
    @groups: -1001394505089

announcement-3 =
    @message: msg-donate
    @every: 19800-23400
    @groups: -1001394505089

announcement-4 =
    @message: msg-website
    @every: 16200-19800
    @groups: -1001394505089

announcement-5 =
    @message: msg-share-bot
    @every: 12600-16200
    @groups: -1001394505089
