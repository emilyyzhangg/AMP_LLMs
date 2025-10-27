##### THESE ARE HOST COMMANDS TO CONTROL THE SERVICES THAT RUN ON LLM.AMPHORAXE.CA #### 

# View All Service Status
launchctl list | grep com.amplm

# Stop/Start all webapp services

launchctl stop com.amplm.webapp
launchctl stop com.amplm.chat
launchctl stop com.amplm.nct
sleep 3
launchctl start com.amplm.webapp
launchctl start com.amplm.chat
launchctl start com.amplm.nct

# Unload/Load Services, one-by-one
launchctl unload ~/Library/LaunchAgents/com.amplm.webapp.plist
launchctl load ~/Library/LaunchAgents/com.amplm.webapp.plist
launchctl unload ~/Library/LaunchAgents/com.amplm.nct.plist
launchctl load ~/Library/LaunchAgents/com.amplm.nct.plist
launchctl unload ~/Library/LaunchAgents/com.amplm.chat.plist
launchctl load ~/Library/LaunchAgents/com.amplm.chat.plist

#####                                       💡 When to use each                                  #######
                            Use case	                                        Recommended command
        Just restart the service executable after code changes	                launchctl stop/start
        You modified the .plist file (paths, environment, KeepAlive, etc.)	    launchctl unload/load
        Service won’t restart or got corrupted	                                launchctl unload/load
        You want to restart everything quickly (like in your update script)	    launchctl stop/start is faster and safer

# Auto-update service
# this service listens for git repo updates, pulls, and restarts all the services
# can be further customized to only restart the modules that it pulled for to avoid full webpage restart
# currently, cloudflare is not caching at all, so this is not an issue

# Restart Auto-Update Service
launchctl unload ~/Library/LaunchAgents/com.amplm.autoupdate.plist 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.amplm.autoupdate.plist

# Watch auto-updater log
tail -f /tmp/amp_autoupdate.log
tail -f /tmp/amp_autoupdate_dev.log

test update
#