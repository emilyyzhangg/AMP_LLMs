launchctl stop com.amplm.webapp
launchctl stop com.amplm.chat
launchctl stop com.amplm.nct

# Wait
sleep 5

# Start all services
launchctl start com.amplm.webapp
launchctl start com.amplm.chat
launchctl start com.amplm.nct