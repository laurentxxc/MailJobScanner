# Project concepts

I am currently looking for new job. I have setup lof of job alerts on different job portals and I regularly received lot of emails coming from these alerts. All these emails are currently automatically moved in dedicated email folder.
I would like to have a automated workflow that can scan a job alert email. This workflow is specified as follow:

1. As an job alert email can contain several job proposals, the email must be scanned (can be AI scan) in order to identify each job proposal and particularly the following attributes:
* Job title
* Job url link description
* Company proposing the job
* Salary (if mentioned)
* Remote job or office location (if mentioned)

2. For each job proposal
	1. Details of the job must be extracted from the link in text format and pass to an AI assistant which must analyse the job description and report answer with the following concerns:
		1. How much job proposal detail matches with my professional experiences. My experience is in a markdown file. Answer must include:
			*. A match level: Low,  Medium or High
			*. A match summary: small description of the how job proposal is matching   

		2. What's the level match between job proposal and my motivation and expectation. My motivation and expectation are in single markdown file. Answer must include:
			* A match level: Low, Medium or High
			* A match summary: small description of the how job proposal is matching   

	2. Log AI report in a database (could be sqlite) with new entry. Following information need to be logged:
		* Job title
		* Job url link description
		* Job company
		* Salary (optional)
		* Location/remote
		* Resume matching level
		* Resume matching description
		* Expectation/motivation matching level
		* Expectation/Motivation matching description

	3. If email contains on or more job proposals that have been analysed with high match levels then email must be flagged with a yellow flag
	