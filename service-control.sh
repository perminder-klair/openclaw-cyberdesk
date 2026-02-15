#!/bin/bash
# Quick service management for OpenClaw CyberDeck

case "$1" in
    start)
        systemctl --user start openclaw-cyberdeck.service
        ;;
    stop)
        systemctl --user stop openclaw-cyberdeck.service
        ;;
    restart)
        systemctl --user restart openclaw-cyberdeck.service
        ;;
    status)
        systemctl --user status openclaw-cyberdeck.service
        ;;
    logs)
        journalctl --user -u openclaw-cyberdeck.service -f
        ;;
    enable)
        systemctl --user enable openclaw-cyberdeck.service
        ;;
    disable)
        systemctl --user disable openclaw-cyberdeck.service
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|enable|disable}"
        exit 1
        ;;
esac
