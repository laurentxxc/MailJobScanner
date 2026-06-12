property projectDir : "/Users/lvt/Documents/Dev/MailJobScan"
property venvPython : projectDir & "/.venv/bin/python3"

on run
	tell application "Mail"
		set selectedMessages to selection
		if selectedMessages is {} then
			display dialog "Please select one or more job alert emails first."
			return
		end if

		do shell script "mkdir -p /tmp/mailjobscan"
		set processedCount to 0

		repeat with msg in selectedMessages
			set msgId to message id of msg
			set tempFile to "/tmp/mailjobscan/" & msgId & ".eml"

			-- Remove existing file then create a fresh one (avoids "already open" error on re-runs)
			do shell script "rm -f " & quoted form of tempFile
			set f to open for access tempFile with write permission
			set eof of f to 0
			write (source of msg) to f
			close access f

			-- Run Python scanner
			set cmd to "cd " & quoted form of projectDir & " && " & venvPython & " main.py " & quoted form of tempFile
			try
				set output to do shell script cmd
				set isFlagged to do shell script "echo " & quoted form of output & " | python3 -c \"import sys,json; d=json.load(sys.stdin); print('true' if d.get('flagged') else 'false')\""
				if isFlagged is "true" then
					set flag index of msg to 1
				end if
				set processedCount to processedCount + 1
			on error errMsg
				display dialog "Error processing message: " & errMsg
			end try
		end repeat

		-- Cleanup temp files
		do shell script "rm -f /tmp/mailjobscan/*.eml"

		display dialog "Done. Processed " & processedCount & " email(s). Results saved to jobscan.db."
	end tell
end run
