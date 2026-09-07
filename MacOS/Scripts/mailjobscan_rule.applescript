property projectDir : "/Users/lvt/Documents/Dev/MailJobScan"
property venvPython : projectDir & "/.venv/bin/python3"

using terms from application "Mail"
	on perform mail action with messages matchedMessages for rule theRule
		tell application "Mail"
			do shell script "mkdir -p /tmp/mailjobscan"

			repeat with msg in matchedMessages
				set msgId to message id of msg
				set tempFile to "/tmp/mailjobscan/" & msgId & ".eml"

				set msgSource to source of msg as Unicode text

				do shell script "rm -f " & quoted form of tempFile
				set f to open for access tempFile with write permission
				set eof of f to 0
				write msgSource to f
				close access f

				set cmd to "cd " & quoted form of projectDir & " && " & venvPython & " main.py " & quoted form of tempFile
				try
					set output to do shell script cmd
					set isFlagged to do shell script "echo " & quoted form of output & " | python3 -c \"import sys,json; d=json.load(sys.stdin); print('true' if d.get('flagged') else 'false')\""
					if isFlagged is "true" then
						set flag index of msg to 3
					end if
					set read status of msg to true
				end try
			end repeat

			do shell script "rm -f /tmp/mailjobscan/*.eml"
		end tell
	end perform mail action with messages
end using terms from
