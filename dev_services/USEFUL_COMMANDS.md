# Make the dev autoupdate script executable

chmod +x ~/Developer/AMP_LLMs/amp_autoupdate_dev.sh

# unload services

launchctl unload ~/Library/LaunchAgents/com.amplm.autoupdate.dev.plist
launchctl unload ~/Library/LaunchAgents/com.amplm.webapp.dev.plist
launchctl unload ~/Library/LaunchAgents/com.amplm.nct.dev.plist
launchctl unload ~/Library/LaunchAgents/com.amplm.chat.dev.plist

# Load all dev services

launchctl load ~/Library/LaunchAgents/com.amplm.autoupdate.dev.plist
launchctl load ~/Library/LaunchAgents/com.amplm.webapp.dev.plist
launchctl load ~/Library/LaunchAgents/com.amplm.nct.dev.plist
launchctl load ~/Library/LaunchAgents/com.amplm.chat.dev.plist
