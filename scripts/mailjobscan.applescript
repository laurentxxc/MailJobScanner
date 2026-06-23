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
		do shell script "echo '---' >> /tmp/mailjobscan/debug.log"
		set processedCount to 0
		
		repeat with msg in selectedMessages
			set msgId to message id of msg
			set tempFile to "/tmp/mailjobscan/" & msgId & ".eml"
			
			-- Force Mail to fully download the message body before reading source
			set msgSource to source of msg as Unicode text
			
			-- Write raw email source to temp file
			do shell script "rm -f " & quoted form of tempFile
			set f to open for access tempFile with write permission
			set eof of f to 0
			write msgSource to f starting at eof
			close access f
			-- save msg in f
			
			-- Log file size for debug comparison
			do shell script "wc -c " & quoted form of tempFile & " >> /tmp/mailjobscan/debug.log"
			
			-- Run Python scanner
			set cmd to "cd " & quoted form of projectDir & " && " & venvPython & " main.py " & quoted form of tempFile
			try
				set output to do shell script cmd
				set isFlagged to do shell script "echo " & quoted form of output & " | python3 -c \"import sys,json; d=json.load(sys.stdin); print('true' if d.get('flagged') else 'false')\""
				if isFlagged is "true" then
					set flag index of msg to 3 -- 0=red, 1=orange, 2=yellow, 3= green, 4=light blue, 5=dark blue, 6=grey
				end if
				set read status of msg to true
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