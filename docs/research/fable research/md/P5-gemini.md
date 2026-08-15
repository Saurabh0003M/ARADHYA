<!-- source: gemini/Legal Status of AI Assistants.docx | converted 2026-08-07 -->

# Legal and Regulatory Analysis of Human-Supervised Personal AI Assistants in India (August 2026)

## Executive Summary

The rapid integration of artificial intelligence into daily digital workflows has necessitated a fundamental re-evaluation of Indian cyber jurisprudence. As of August 2026, the deployment of personal AI assistants—specifically those designed to automate repetitive digital tasks such as form filling, message drafting, and page navigation—operates at the complex intersection of the Information Technology (IT) Act, 2000, the Digital Personal Data Protection (DPDP) Act, 2023, and the highly fragmented, often reactive Terms of Service (ToS) agreements enforced by both state e-governance portals and private commercial platforms.

This report provides an exhaustive, multi-layered legal, regulatory, and policy analysis of a specific operational paradigm: a human-supervised personal AI assistant operating entirely on an individual's local machine, managing their own accounts. The critical technological parameters defining this assistant are its structural reliance on human confirmation gates, its hardcoded restriction against autonomously solving Completely Automated Public Turing tests to tell Computers and Humans Apart (CAPTCHAs) or One-Time Passwords (OTPs), and its inability to execute final data submissions. By isolating these parameters, this analysis delineates the boundaries between benign technological enhancement (which facilitates human activity) and unauthorized computer access (which simulates or replaces human activity).

The following sections systematically deconstruct the statutory framework governing digital access and data processing, the enforcement realities of Indian government portals and private job platforms, the evolving norms surrounding AI-authorship disclosure, and the legal consequences of security circumvention. The report concludes with a categorized strategic deliverable outlining the definitive legal standing of various automated actions within the Indian digital ecosystem.

## Part I: The Statutory Baseline for Access and Security Circumvention

To determine the legality of a local, human-supervised AI assistant, it is essential to first examine the statutory pillars of Indian digital law, primarily the Information Technology Act, 2000, and the judicial precedents surrounding the circumvention of cybersecurity mechanisms.

### 1. The Information Technology Act, 2000: Access, Authorization, and Intent

The IT Act, 2000, establishes the baseline for lawful interaction with computer resources in India. The legality of an AI assistant navigating pages and autofilling forms hinges entirely on the interpretation of "authorization" and "unauthorized access" under Sections 43 and 66 of the Act.

Section 43: Civil Liability for Unauthorized Access Section 43 of the IT Act imposes strict civil liability on any person who, "without permission of the owner or any other person who is in charge of a computer, computer system or computer network," accesses, downloads, copies, or extracts data, or introduces any computer contaminant1. The penalty for such infractions is a compensation mandate that can extend up to ₹1 crore payable to the affected party1. The critical legal threshold here is the "permission of the owner."

When an individual utilizes a personal AI assistant on their own computer to navigate their own accounts, they are acting as the authorized user of the local machine and the authorized credential holder of the remote account. However, the "computer system" in question also includes the remote servers hosted by government entities or private platforms. If a platform's Terms of Service explicitly prohibit automated scripts, the use of such a script theoretically exceeds the scope of the user's authorization, technically triggering Section 431. Judicial interpretations in India have established that exceeding authorized access limits—even using legitimate credentials—can invoke Section 43, as demonstrated in various corporate data breach cases where employees misused their access4.

Nevertheless, the practical enforcement of Section 43 requires the affected platform to prove actual damages resulting from the unauthorized access4. A local script that merely types data at human speed to autofill a form, without causing a Denial of Service (DoS), degrading server performance, or scraping proprietary backend databases, rarely generates the requisite quantifiable damages to invite civil prosecution4.

Section 66: Criminal Liability and the Requirement of Mens Rea Section 66 elevates the civil wrongs delineated in Section 43 to criminal offenses—punishable by up to three years of imprisonment and a ₹5 lakh fine—if the act is committed "dishonestly or fraudulently"2. This introduces the strict requirement of mens rea (criminal intent).

For a human-supervised AI assistant that autofills a user's genuine profile data into legitimate forms, the mens rea for fraud or dishonesty is structurally absent5. The user is not attempting to deceive the platform about their identity, nor are they attempting to steal data or compromise system integrity. The assistant is merely acting as a sophisticated, automated keyboard interface. Because the tool operates under human supervision and relies on the human for security gates, it prevents the kind of autonomous, high-velocity systemic abuse that courts have traditionally classified as criminal hacking under Section 664. The distinction between Section 43 and Section 66 is paramount: while automation might constitute a civil breach of a platform's terms under Section 43, it lacks the fraudulent intent required for criminal prosecution under Section 66, provided the underlying activity (e.g., applying for a job or renewing a certificate) is legitimate.

| IT Act Provision | Scope and Nature | Penalty / Liability | Relevance to Personal AI Assistant |
|---|---|---|---|
| Section 43 | Civil liability for unauthorized access, data extraction, or network disruption. | Compensation up to ₹1 crore2. | Technical breach possible if platform ToS bans scripts, but lack of damages prevents practical enforcement4. |
| Section 66 | Criminal hacking; committing acts in Section 43 "dishonestly or fraudulently." | Imprisonment up to 3 years; Fine up to ₹5 lakh2. | Not applicable. Utilizing a tool to autofill own legitimate data lacks fraudulent intent (mens rea)4. |

### 2. The Legal Boundary of CAPTCHAs and OTPs

The most legally protective feature of the AI assistant described in the prompt is its strict limitation against solving CAPTCHAs, entering OTPs, and executing the final submission. Under Indian cyber law, the circumvention of these specific security gates marks the definitive boundary between a benign productivity tool and an illegal hacking instrument.

The IRCTC Tatkal Precedents The Indian legal system's stance on automated form-filling is heavily informed by the railway ticketing (Tatkal) arrests that occurred prominently between 2020 and 2023. Developers created mobile applications and browser extensions that automated the filling of the IRCTC Tatkal booking forms, allowing users to secure highly competitive train tickets in seconds8. Crucially, these illicit tools included features to automatically bypass CAPTCHAs and intercept OTPs, allowing users to book tickets at superhuman speeds8.

The Railway Protection Force (RPF) and the Central Bureau of Investigation (CBI) launched massive crackdowns, arresting developers and users under Section 143(2) of the Railways Act (unauthorized carrying on of the business of procuring and supplying railway tickets) and Section 66 of the IT Act (hacking)8. The authorities established that developing or utilizing software to bypass e-ticketing security systems defeated the equitable, first-come-first-serve architecture of the platform, constituting a criminal offense8.

The Human-in-the-Loop Insulator By deliberately offloading CAPTCHA resolution and OTP entry to the human operator, a personal AI assistant avoids the exact mechanisms that triggered criminal liability in the Tatkal cases.

CAPTCHAs: A CAPTCHA is a definitive, court-recognized technological barrier designed to enforce human interaction and prevent bulk abuse8. Bypassing it via optical character recognition (OCR) or third-party solving APIs is viewed by Indian courts and enforcement agencies as an active circumvention of a platform's cybersecurity architecture, fulfilling the criteria for unauthorized access under Section 43(a) and potentially Section 661.

OTPs: OTPs are a form of multi-factor authentication (MFA) tied directly to the user's verified identity (mobile device or Aadhaar linkage). They are legally mandated for services ranging from Tatkal bookings (since July 2025)9 to Aadhaar updates10. Automating the interception and entry of an OTP touches upon identity impersonation and security circumvention8.

Confirmation Gates: Because the AI assistant stops and requires the human to click the final "Submit" button, the human assumes full legal authorship and liability for the data transmitted. The software remains a passive conduit for preparation, not an autonomous agent of execution. This architectural choice virtually eliminates the risk of criminal prosecution under Section 66 of the IT Act, as the final intentional act of data submission is demonstrably human4. The law is effectively silent on penalizing software that merely stages data for human approval, provided the underlying security mechanisms remain intact.

## Part II: The DPDP Act, 2023: Data Principals, Fiduciaries, and Exemptions

The Digital Personal Data Protection (DPDP) Act, 2023, fully operationalized by the 2025 Rules and currently in its phased implementation period concluding in 2027, fundamentally alters how personal data is handled in India12. The Act applies explicitly to the processing of digital personal data within Indian territory, and exercises extraterritorial jurisdiction if processing targets individuals in India12. However, the applicability of the Act depends entirely on whose data the AI assistant is processing and for what purpose. Notably, the DPDP Act does not sub-classify data; it treats all digital personal data equally, eliminating previous concepts of "sensitive" personal data15.

### 1. Processing Own Data: The Personal and Domestic Exemption

Section 3(c)(i) of the DPDP Act explicitly states that the Act does not apply to "personal data processed by an individual for any personal or domestic purpose"14. This clause, often referred to as the "household exemption," is a statutory recognition of negative liberty—the freedom of an individual to manage their own private affairs without state regulatory intrusion18.

When the human owner of the AI assistant uses the software locally to draft personal emails, autofill their own Aadhaar details, manage their own digital diary, or apply for jobs using their own resume, the entire processing lifecycle is entirely exempt from the DPDP Act18. The software is acting merely as an extension of the individual's domestic life. There are no obligations to maintain verifiable consent logs, issue privacy notices in the 22 scheduled Indian languages, or report data breaches to the Data Protection Board of India, because the Act simply does not apply to this localized, personal activity12.

Furthermore, Section 3(c)(ii) provides an exemption for "personal data that is made or caused to be made publicly available by the Data Principal"14. If the AI assistant drafts a message based on a recruiter's publicly available LinkedIn profile, this processing is also exempt from the Act, provided the recruiter voluntarily made the data public14.

### 2. Processing Client Data: Crossing the Commercial Threshold

The legal reality shifts dramatically if the user employs the same AI assistant to process a freelance client's data—for instance, an independent consultant using the AI to read a client's proprietary documents to draft replies, or a virtual assistant autofilling forms on behalf of the client.

The moment the processing moves from a "personal or domestic purpose" to a commercial, professional, or freelance purpose, the Section 3(c)(i) exemption evaporates18. The freelance user legally becomes a "Data Fiduciary" (or at minimum, a Data Processor acting on behalf of a Data Fiduciary), subject to the full weight of the DPDP Act12. This transition triggers severe compliance requirements:

Notice and Consent (Sections 5 & 6): The freelancer must provide a clear notice and obtain free, specific, informed, unconditional, and unambiguous consent from the client before feeding their personal data into the AI assistant12. The client must be informed exactly how their data will be processed by the AI.

Reasonable Security Safeguards (Section 8): Under Section 8, the freelancer is statutorily obligated to implement reasonable security safeguards to prevent data breaches12. If the local AI assistant transmits the client's personal data to a remote Large Language Model (LLM) API without robust encryption or data processing agreements ensuring privacy, the freelancer is strictly liable for any resulting data exposure, facing potential penalties of up to ₹250 crore from the Data Protection Board12.

Data Minimization and Retention: The AI assistant must be configured to forget or delete the client's data once the specific drafting task is completed, adhering to the purpose limitation and data retention mandates15.

| Processing Scenario | Data Subject | DPDP Act 2023 Applicability | Statutory Obligations |
|---|---|---|---|
| Personal Use | Self (Owner) | Exempt (Sec 3(c)(i))14 | None. Purely domestic/personal use18. |
| Public Data Use | Third Party (Public) | Exempt (Sec 3(c)(ii))14 | None, if data was voluntarily made public by the Data Principal18. |
| Commercial Use | Freelance Client | Fully Applicable [cite: 18, 22] | Must obtain consent, ensure API security (Sec 8), and delete data post-use15. |

## Part III: E-Governance and State Portals

Indian government portals have undergone massive digital transformations, centralizing citizen data through Aadhaar, DigiLocker, and various state-level e-district platforms. The terms of use across these platforms reflect a unified, defensive hostility toward automated access, primarily to protect against bulk data scraping, equitable access violations, and denial-of-service attacks. However, a nuanced gap exists between the published ToS and the enforcement actions against individual, supervised form-filling.

The prompt explicitly asks: is assisted form-filling with a human present and confirming each submission treated differently from bot access anywhere? The answer is that while the law (IT Act) treats it differently due to the lack of security circumvention, the published Terms of Service of state portals generally fail to make this distinction, utilizing blanket bans on all automation.

### 1. UIDAI and Aadhaar Services

The Unique Identification Authority of India (UIDAI) manages the myAadhaar portal, handling highly sensitive demographic and biometric updates, governed by regulations updated through 202610. The official UIDAI Website Policy and Terms & Conditions state:

"Users shall not attempt to misuse, disrupt, or compromise the security of the website or associated portals. Any unauthorized attempt to access, modify, or misuse data may lead to appropriate legal action as per applicable laws."

[cite: 10, 25]

Furthermore, UIDAI mandates user authentication through OTPs for almost all services (e.g., address updates, e-KYC, Aadhaar downloads)10. While the ToS strictly prohibits actions that compromise security, they do not explicitly contain the words "script," "bot," or "automation" in the public-facing citizen terms, focusing instead on the broader concept of "unauthorized access"10. Because the AI assistant operates locally, uses the citizen's own credentials, and pauses to allow the citizen to input the Aadhaar OTP, the assistant acts merely as a client-side interface tool. As long as it does not attempt bulk demographic scraping or attempt to hit UIDAI APIs at superhuman speeds, supervised local autofill remains a technically tolerated, albeit gray, area.

### 2. DigiLocker

Operated by the National e-Governance Division (NeGD) under MeitY, DigiLocker is the backbone of paperless governance in India, holding immense repositories of verified citizen documents. Its Terms of Use are substantially more explicit regarding automation than UIDAI's. The DigiLocker Acceptable Use Policy explicitly prohibits users from using the platform to:

"Host malware, other schemes such as phishing, or other technology intended to cause unauthorized access, stealing data, or damage to infrastructure."

[cite: 27]

More explicitly, the EntityLocker (the organizational counterpart to DigiLocker) terms state that users are prohibited from engaging in activities that disrupt the platform, including hacking, introducing malware, or unauthorized data access28. Furthermore, third-party aggregators outlining acceptable use policies indicate that automated harvesting (crawling, scraping, spidering, bulk download, data extraction) is strictly prohibited without prior written consent27.

However, DigiLocker also emphasizes that "Users retain complete ownership of all content that they upload, store, share, or transmit through the DigiLocker platform"27. Because the AI assistant operates entirely on the client-side Document Object Model (DOM) to organize the user's own owned documents, and does not conduct backend API scraping, it bypasses the traditional definitions of a malicious crawler. Nevertheless, utilizing an automated script on DigiLocker remains in a legal gray zone due to the broad definitions of "unauthorized access" in the ToS27.

### 3. Passport Seva

The Passport Seva portal, managed by the Ministry of External Affairs, is notoriously sensitive due to national security implications and high demand. Applications require precise form-filling and stringent appointment booking procedures. The portal utilizes CAPTCHAs extensively to prevent bulk appointment booking by unauthorized travel agents and touts8.

The Passport Seva website policy states that personal information shall be used only for its intended purpose and records server logs to monitor security31. While the public ToS lacks a specific clause banning "browser extensions," the backend infrastructure is aggressively tuned to detect and block scripts, stemming directly from historical battles with Tatkal-style appointment booking bots8. Using an AI assistant to purely draft the text of a complex application offline and then paste it into the Passport Seva form is perfectly legal. However, allowing the script to rapidly navigate the appointment booking calendar or autofill fields faster than humanly possible risks triggering automated temporary IP bans by the portal's Web Application Firewall (WAF).

### 4. State Portals (Aaple Sarkar) and Employment Exchanges (NCS/SSC)

State-level e-district portals like Maharashtra's Aaple Sarkar and central employment portals like the National Career Service (NCS) and Staff Selection Commission (SSC) exhibit standard anti-scraping postures, utilizing blanket terminology.

Aaple Sarkar: Third-party aggregators and terms of use for Mahaonline/Aaple Sarkar information explicitly warn users not to "Scrape, republish or resell our pages wholesale, or run automated requests that degrade the site for other people" or "Attempt to break, probe or interfere with the site, its hosting, or its security"33.

SSC: The Staff Selection Commission (SSC) explicitly prohibits the use of "any automated scraping, crawling, or data mining tools against the Platform"34.

NCS: The National Career Service portal frequently warns users against fraudulent entities and maintains strict control over job-seeker data access, operating as a centralized hub for employment matching36.

The Enforcement Reality vs. Written Terms: Across all Indian government portals, the enforcement paradigm is reactive and threat-based. Portals do not actively prosecute individual citizens whose local browser extensions autofill their own names, educational details, and addresses into an SSC form or an Aaple Sarkar domicile certificate application. Prosecution under the IT Act is strictly reserved for actors who bypass security (CAPTCHAs/OTPs) to commercialize access, hoard appointments, extract bulk data, or cause server degradation4. Therefore, a supervised, human-gated autofill tool operates safely beneath the threshold of prosecutorial interest, despite technically brushing against broad anti-automation ToS clauses that fail to distinguish between assistive technologies and autonomous bots.

## Part IV: Private Sector Job Platforms and Professional Networks

The private sector presents a contrasting regulatory environment. Platforms like LinkedIn, Naukri, and Indeed are driven by the commercial value of their proprietary data moats. In 2026, the battle between platforms and automated tools is highly sophisticated, relying heavily on behavioral analytics and AI-detection software rather than mere statutory threats. Unlike government portals, private platforms aggressively ban user accounts for ToS violations.

### 1. LinkedIn: The Safe Harbor for Enhancing Extensions

LinkedIn possesses one of the most rigorously litigated and highly specific User Agreements regarding automation, actively enforcing its policies. In a single quarter of 2026, LinkedIn's Transparency Report noted the flagging of 23.5 million automated sessions and the blocking of 78.2 million fake accounts38.

Section 8.2 of LinkedIn's User Agreement strictly prohibits members from using "bots or other unauthorized automated methods to access the Services" and explicitly bans developing or using "software, devices, scripts, robots or any other means or processes (such as crawlers, browser plugins and add-ons or any other technology) to scrape or copy the Services"39. Violations result in swift account restrictions and permanent bans40. Cloud-based automation tools that simulate sessions on remote servers (e.g., Expandi, Dripify, and the recently banned HeyReach) are strictly prohibited because they route accounts through infrastructure that is not the user's, simulating human activity38.

However, the 2024–2026 iterations of the LinkedIn User Agreement introduced a critical safe harbor. As analyzed by industry legal observers, Clause 8.3 explicitly permits "browser extensions that enhance the user's own experience," provided they do not scrape data in violation of Clause 8.2 or send messages without the user's review43. Furthermore, Clause 11, which outlines account restriction triggers, specifically targets tools that "simulate or impersonate human activity"43.

This creates a clear legal runway for the human-supervised personal AI assistant defined in this report. Because the assistant (a) operates entirely inside the actual browser on the user's own machine, (b) requires the human to click the final "Submit" or "Send" button, and (c) does not engage in unattended background scraping or bulk messaging, it acts as an "enhancing extension" rather than a prohibited bot38. It does not simulate human activity; it facilitates actual human activity. Therefore, using this specific type of assistant on LinkedIn to draft messages or format profile data is TOS-compliant as of August 202643.

### 2. Naukri: Strict Anti-Extraction and the Threat of AI Verification

Naukri.com enforces stringent rules to protect its massive resume database and job listings. The Naukri Campus Terms and Conditions explicitly prohibit:

"Extracting data from NC using any automated process such as spiders, crawlers etc. or through any manual process... Access the Platform for purposes of extracting content to be used for training a machine learning or AI model, without the express prior written permission."

[cite: 44]

While a local AI assistant autofilling a job application does not strictly "extract" data for model training, the overarching ban on automated processes creates a hostile environment for automation44. More importantly, Naukri's platform mechanics in 2026 represent a severe practical barrier for AI tools. According to industry data, 65% of large Indian IT recruiters utilize AI-checking software (such as GPTZero, Originality, Copyleaks, or proprietary Applicant Tracking System (ATS) parsers like Resume Worded) to scan incoming resumes and cover letters45.

These ATS parsers are designed to flag and auto-reject applications that exhibit high AI-authorship scores, use non-standard formatting (like two-column layouts or complex tables), or utilize generic robotic phrasing (e.g., "delve into," "in today's landscape")45. Therefore, while using an AI assistant to apply for jobs on Naukri might not result in civil litigation against the user, it carries a massive practical risk of algorithmic shadow-banning or automated rejection by recruiters' screening tools if the AI-generated text is not heavily humanized and localized with specific, verifiable metrics46.

### 3. Indeed (India): Definitions of Agentic AI

Indeed's 2026 legal framework formally recognizes the existence of AI tools. Their terms define "Agentic AI" as an algorithm capable of performing tasks based on human instructions, noting that it "often has a chat interface" and "does not have autonomy or personhood"47. They also define "AI-Generated Content"47.

While Indeed strictly regulates API access and prohibits unauthorized scraping48, they do not explicitly ban a user from utilizing a local Agentic AI assistant to help draft cover letters or fill out the "Indeed Apply" fields, provided the user is not attempting to reverse-engineer the platform or submit thousands of spam applications47. Indeed Apply systems are integrated tightly with Employer Applicant Tracking Systems (ATS), requiring compliance with specific formatting guidelines49. Thus, supervised AI assistance is tolerated for individual application enhancement, provided it does not cross into bulk spamming.

| Platform | Automation / Bot Policy | Human-in-the-Loop AI Policy | Enforcement Reality (2026) |
|---|---|---|---|
| LinkedIn | Strictly banned (Section 8.2)40. | Permitted (Section 8.3) if reviewed by human43. | Actively bans headless/cloud bots; permits local supervised drafting extensions38. |
| Naukri | Strictly banned for extraction/training44. | Gray area; no explicit ban on drafting, but highly risky. | Heavy use of AI-checkers by recruiters leads to widespread auto-rejections of AI-generated text46. |
| Indeed | Regulated via API; scraping banned47. | Acknowledged ("Agentic AI" defined)47. | Tolerated for individual application enhancement, subject to ATS formatting constraints49. |

## Part V: AI-Authorship Disclosure: Regulatory Advisories and Professional Norms

As AI drafting becomes ubiquitous in 2026, the regulatory focus in India is slowly shifting toward transparency and disclosure. However, the mandate to disclose AI authorship depends entirely on the context of the communication. In many professional arenas, the law remains notably silent, leaving disclosure to ethical norms and contractual agreements.

### 1. Government and Judiciary Advisories

The Ministry of Electronics and Information Technology (MeitY) has issued various advisories regarding AI, primarily targeting social media intermediaries to label "synthetically created" content. The objective of these advisories is to combat deepfakes and electoral misinformation50. These advisories do not currently extend to private citizens using AI to draft mundane text, fill out forms, or write professional emails.

In the judicial sphere, the Supreme Court of India's draft guidelines on AI in Courts (2026) establish that AI recommendations remain strictly advisory52. For legal practitioners, the Bar Council of India (BCI) treats AI use under general ethical duties of professional competence and client confidentiality. If a lawyer uses a personal AI assistant to draft a client reply, they bear ultimate responsibility for the output. If the AI hallucinates a legal precedent and the lawyer submits it to a court, the liability falls entirely on the lawyer, not the tool. There is no statutory requirement to disclose the use of a drafting tool to a judge, but the ethical burden of accuracy is absolute.

### 2. Commercial and Freelance Communications

The Advertising Standards Council of India (ASCI) guidelines mandate that influencers and advertisers disclose the use of AI-generated content in marketing materials50. However, for a freelance professional using an AI assistant to draft client emails, format reports, or generate code, there is currently no statutory rule under Indian law requiring the disclosure of AI drafting50.

It remains purely an ethical consideration and a matter of contractual agreement. If a freelancer's contract explicitly requires human-authored original work, utilizing an AI assistant without disclosure constitutes a breach of contract, but it is not a statutory cybercrime under the IT Act. The law is simply silent on penalizing the undisclosed use of AI for routine professional drafting.

## Part VI: Strategic Deliverables – The Categorized Legal Reality

Based on the exhaustive analysis of Indian statutes, judicial precedents, and 2026 platform Terms of Service, the legal reality for a human-supervised personal AI assistant (that never solves CAPTCHAs, OTPs, or final submits, and runs locally) is categorized below:

### 🟩 CLEARLY FINE (Legally Safe & Permitted)

Drafting and Autofilling Personal Data for Domestic Use: Utilizing the assistant on your own computer to draft text and autofill forms using your own personal data (e.g., job applications, personal diaries).

Source: DPDP Act 2023, Section 3(c)(i) (Personal or domestic purpose exemption), which protects negative liberty and removes data compliance burdens14.

Using AI for Supervised Drafting on LinkedIn: Utilizing the assistant to draft messages or profile updates on LinkedIn, provided the tool runs locally in the browser and the human clicks the final "Send" or "Save" button.

Source: LinkedIn User Agreement (2024-2026 updates), Clause 8.3 (Permitted Extensions) and Clause 11 (Allows tools that enhance rather than simulate human activity)43.

Architectural Reliance on Human Resolution of CAPTCHAs and OTPs: The software design of pausing to allow the human to manually solve CAPTCHAs and enter OTPs.

Source: IT Act 2000, Section 43/66, and Railways Act Sec 143(2) precedents. By ensuring human resolution, the tool avoids the legal definition of "bypassing security checks" and identity impersonation, which constitute criminal hacking4.

Drafting Client Communications Without Statutory Disclosure: Using the AI to draft an email for a client without adding an "AI-generated" disclaimer.

Source: Legal Silence. While ASCI requires disclosure for advertising50, no Indian statute mandates disclosure for general professional or freelance B2B communication. It remains a matter of private contract law.

### 🟨 GRAY (Tolerated but Requires Named Precautions)

Processing a Freelance Client’s Data: Using the assistant to draft replies or fill forms using a client’s personal data.

Precaution: You lose the DPDP "domestic exemption" and legally transition into a Data Fiduciary or Processor. You must ensure the AI tool's backend APIs do not retain the data, and you must obtain the client's informed consent before processing their data through the tool.

Source: DPDP Act 2023, Section 3 (Applicability)18 and Section 8 (Reasonable Security Safeguards)15.

Autofilling Indian Government Portals (UIDAI, Passport Seva, e-Districts): Using the script to navigate pages and paste text into forms on state portals.

Precaution: Strict rate limiting must be enforced. The script must mimic human typing speed and must never attempt to bypass appointment booking queues. While not criminally prosecuted if human-supervised, aggressive script behavior will trigger Web Application Firewalls (WAF) leading to temporary IP bans. The ToS technically bans automation, failing to distinguish between bots and assistive tools.

Source: UIDAI Terms & Conditions (bans unauthorized attempts to access)10; Aaple Sarkar ToS (bans automated requests that degrade the site)33; SSC Copyright Policies (bans automated scraping)34.

Applying for Jobs on Indian Platforms (Naukri, Indeed): Using the assistant to rapidly autofill job applications.

Precaution: Avoid using raw AI-generated text for resumes or cover letters. While not illegal, recruiters in 2026 heavily deploy AI-checking software (ATS parsers, GPTZero). High AI scores result in automated application rejection.

Source: Naukri.com Terms (bans automated data extraction)44; Industry hiring trends and AI-screening adoption rates45.

### 🟥 NEVER (Strictly Prohibited & Legally Actionable)

Automating the Bypass of CAPTCHAs or OTPs: Modifying the assistant to automatically solve CAPTCHAs (via OCR or third-party API solvers) or intercept OTPs from SMS/Email to execute final submissions.

Source: IT Act 2000, Section 43 (Unauthorized Access) and Section 66 (Hacking); firmly established by the IRCTC/Tatkal arrest precedents where bypassing CAPTCHAs and OTPs resulted in severe criminal prosecution4.

Headless or Unattended Scraping of Platform Data: Leaving the assistant running unattended to scrape job listings, government data, or user profiles to build a local database or train a separate AI model.

Source: DigiLocker Acceptable Use Policy27; SSC Copyright Policies34; Naukri Terms and Conditions44; LinkedIn User Agreement Clause 8.239. This behavior simulates non-human activity, exposing the user to immediate permanent account bans (especially on LinkedIn) and potential civil litigation under Section 43 of the IT Act for unauthorized extraction of data4.

This is for informational purposes only. For legal advice regarding specific compliance strategies under the IT Act 2000 or the DPDP Act 2023, consult a qualified legal professional specializing in Indian cyber law.

#### Works cited

Access related crimes - Department of Information & Communication Technology, [https://dict.mizoram.gov.in/uploads/attachments/0328f4bdf90dbb46e7072c877f759ccc/access-related-crimes.pdf](https://dict.mizoram.gov.in/uploads/attachments/0328f4bdf90dbb46e7072c877f759ccc/access-related-crimes.pdf)

Information Technology Act - IHRPC Human Rights, [https://ihrpchumanrights.com/rights/information-technology-act](https://ihrpchumanrights.com/rights/information-technology-act)

Cyber Crime Punishment in India (IT Act Sections, Fines & Jail Terms) - Testbook, [https://testbook.com/ugc-net-commerce/cyber-crimes-penalties](https://testbook.com/ugc-net-commerce/cyber-crimes-penalties)

Navigating the Legal Landscape of Hacking and Unauthorized Access - The Law Institute, [https://thelaw.institute/regulation-of-cyberspace/legal-consequences-hacking-unauthorized-access/](https://thelaw.institute/regulation-of-cyberspace/legal-consequences-hacking-unauthorized-access/)

All you need to know about hacking - iPleaders, [https://blog.ipleaders.in/all-you-need-to-know-about-hacking/](https://blog.ipleaders.in/all-you-need-to-know-about-hacking/)

Understanding Data Theft Under IT Act, 2000: Laws, Penalties, and Prevention, [https://finlawassociates.com/blog/understanding-data-theft-under-it-act-2000-laws-penalties-and-prevention](https://finlawassociates.com/blog/understanding-data-theft-under-it-act-2000-laws-penalties-and-prevention)

Information Technology (amendment) Act, 2008 : An Overview - manupatra articles, [https://articles.manupatra.com/article-details/Information-Technology-amendment-Act-2008-An-Overview](https://articles.manupatra.com/article-details/Information-Technology-amendment-Act-2008-An-Overview)

Indian developer jailed for making unauthorized train ticket booking app - Hacker News, [https://news.ycombinator.com/item?id=25121465](https://news.ycombinator.com/item?id=25121465)

Morning News | DD News On Air - Newsonair, [https://www.newsonair.gov.in/bulletins-detail/morning-news-401/](https://www.newsonair.gov.in/bulletins-detail/morning-news-401/)

Website Policy - Unique Identification Authority of India, [https://uidai.gov.in/website-policies](https://uidai.gov.in/website-policies)

FAQs - DigiLocker, [https://www.digilocker.gov.in/web/about/faq](https://www.digilocker.gov.in/web/about/faq)

Digital Personal Data Protection Act, 2023 - Wikipedia, [https://en.wikipedia.org/wiki/Digital_Personal_Data_Protection_Act,_2023](https://en.wikipedia.org/wiki/Digital_Personal_Data_Protection_Act,_2023)

Data protection laws in India, [https://www.dlapiperdataprotection.com/?t=law&c=IN](https://www.dlapiperdataprotection.com/?t=law&c=IN)

Section 3 in THE DIGITAL PERSONAL DATA PROTECTION ACT, 2023 - Indian Kanoon, [https://indiankanoon.org/doc/84660522/](https://indiankanoon.org/doc/84660522/)

The Digital Personal Data Protection Act, 2023 | PwC India, [https://www.pwc.in/assets/pdfs/consulting/risk-consulting/the-digital-personal-data-protection-act-india-2023.pdf](https://www.pwc.in/assets/pdfs/consulting/risk-consulting/the-digital-personal-data-protection-act-india-2023.pdf)

Digital Personal Data Protection Act, 2023 – Key Highlights - AZB & Partners, [https://www.azbpartners.com/bank/digital-personal-data-protection-act-2023-key-highlights/](https://www.azbpartners.com/bank/digital-personal-data-protection-act-2023-key-highlights/)

What is the DPDP Act 2023? India's Data Privacy Law Explained - miniOrange, [https://www.miniorange.com/blog/what-is-dpdp-act/](https://www.miniorange.com/blog/what-is-dpdp-act/)

Digital Personal Data Protection Act, 2023 DPDPA SECTION 3 WITH INTERPRETATION, [https://www.dpdpa.com/dpdpa2023/chapter-1/section3.html](https://www.dpdpa.com/dpdpa2023/chapter-1/section3.html)

THE DIGITAL PERSONAL DATA PROTECTION ACT, 2023 (NO. 22 OF 2023) An Act to provide for the processing of digital personal data in, [https://www.meity.gov.in/static/uploads/2024/06/2bf1f0e9f04e6fb4f8fef35e82c42aa5.pdf](https://www.meity.gov.in/static/uploads/2024/06/2bf1f0e9f04e6fb4f8fef35e82c42aa5.pdf)

India DPDP Act 2023: Compliance Checklist for Global Organizations - Glocert International, [https://www.glocertinternational.com/resources/guides/dpdp-india-compliance-checklist](https://www.glocertinternational.com/resources/guides/dpdp-india-compliance-checklist)

Section 3(c) in THE DIGITAL PERSONAL DATA PROTECTION ACT, 2023 - Draft Bot Pro, [https://app.draftbotpro.com/doc/115332071](https://app.draftbotpro.com/doc/115332071)

Digital Personal Data Protection Act | Data Privacy India - Seqrite, [https://www.seqrite.com/understanding-data-privacy-and-dpdp-act/](https://www.seqrite.com/understanding-data-privacy-and-dpdp-act/)

Rules - Unique Identification Authority of India, [https://uidai.gov.in/en/about-uidai/legal-framework/rules.html](https://uidai.gov.in/en/about-uidai/legal-framework/rules.html)

Regulations - Unique Identification Authority of India | Government of India, [https://uidai.gov.in/en/about-uidai/legal-framework/regulations.html](https://uidai.gov.in/en/about-uidai/legal-framework/regulations.html)

Terms & Conditions - Unique Identification Authority of India, [https://uidai.gov.in/en/terms-conditions.html](https://uidai.gov.in/en/terms-conditions.html)

Privacy Policy - Unique Identification Authority of India | Government of India, [https://uidai.gov.in/en/privacy-policy.html](https://uidai.gov.in/en/privacy-policy.html)

Terms of Use - DigiLocker, [https://www.digilocker.gov.in/web/about/tos](https://www.digilocker.gov.in/web/about/tos)

Terms of Service - EntityLocker - DigiLocker, [https://entity.digilocker.gov.in/web/about/tos](https://entity.digilocker.gov.in/web/about/tos)

Terms and Conditions - Shine, [https://www.shine.com/termsandconditions](https://www.shine.com/termsandconditions)

Contact Us - Passport Seva, [https://www.passportindia.gov.in/psp/contactUs](https://www.passportindia.gov.in/psp/contactUs)

Privacy Policy - Passport Seva, [https://www.passportindia.gov.in/psp/policy](https://www.passportindia.gov.in/psp/policy)

Transcript of Media Briefing on Passport, Visa and Consular Issues, September 10, 2013, [https://www.mea.gov.in/lok-sabha.htm?dtl/22191/Transcript+of+Media+Briefing+on+Passport+Visa+and+Consular+Issues+September+10+2013](https://www.mea.gov.in/lok-sabha.htm?dtl/22191/Transcript+of+Media+Briefing+on+Passport+Visa+and+Consular+Issues+September+10+2013)

Terms of Use | MahaBhartiLive, [https://mahabhartilive.com/terms/](https://mahabhartilive.com/terms/)

Terms of Service - Sarkaari Saathi, [https://www.sarkaarisaathi.com/terms](https://www.sarkaarisaathi.com/terms)

CopyRight Policies | Staff Selection Commission | GoI - SSC, [https://ssc.gov.in/home/copyright-policies](https://ssc.gov.in/home/copyright-policies)

National Career Service for Job Seekers and Employers, [https://www.india.gov.in/services/details/national-career-service-for-job-seekers-and-employers](https://www.india.gov.in/services/details/national-career-service-for-job-seekers-and-employers)

Pages - Job Details - ncs.gov.in, [https://www.ncs.gov.in/job-seeker/Pages/ViewJobDetails.aspx?A=w1BcJXzB%2BW4%3D&U=&JSID=l%2BXnishGhlQ%3D&RowId=l%2BXnishGhlQ%3D&OJ=dGSbsEVAcMk%3D](https://www.ncs.gov.in/job-seeker/Pages/ViewJobDetails.aspx?A=w1BcJXzB%2BW4%3D&U&JSID=l%2BXnishGhlQ%3D&RowId=l%2BXnishGhlQ%3D&OJ=dGSbsEVAcMk%3D)

LinkedIn Automation Rules 2026: Banned vs. Safe Tools - Northlight, [https://northlight.ai/blog/is-linkedin-automation-against-the-rules](https://northlight.ai/blog/is-linkedin-automation-against-the-rules)

LinkedIn CFAA Data Scraping Litigation Update, [https://natlawreview.com/article/federal-court-rules-favor-linkedin-s-breach-contract-claim-after-six-years-cfaa-data](https://natlawreview.com/article/federal-court-rules-favor-linkedin-s-breach-contract-claim-after-six-years-cfaa-data)

Best LinkedIn Easy Apply Automation Tools in 2026 (And the Risks), [https://www.resumly.ai/best/best-linkedin-easy-apply-automation-tools](https://www.resumly.ai/best/best-linkedin-easy-apply-automation-tools)

LinkedIn Automation Rules 2025–2026: What Is and Isn't Allowed | Salesbot.cz, [https://salesbot.cz/en/blog/linkedin-automation-rules-2025-2026](https://salesbot.cz/en/blog/linkedin-automation-rules-2025-2026)

LinkedIn Automation Limits 2026: Safe Daily & Weekly Caps - Linked Helper, [https://www.linkedhelper.com/blog/linkedin-automation-limits/](https://www.linkedhelper.com/blog/linkedin-automation-limits/)

Is Auto-Applying to LinkedIn Jobs Against TOS? (2026 Legal Guide) | JobApplyAI, [https://jobapplyai.in/blog/is-auto-applying-linkedin-jobs-against-tos/](https://jobapplyai.in/blog/is-auto-applying-linkedin-jobs-against-tos/)

Terms and Conditions - Register on Firstnaukri.com-Apply for Freshers Jobs, [https://cm.naukri.com/?redirect=https%3A%2F%2Fwww.firstnaukri.com%2Ffreshersmnj%2Fmynaukri.php%2FShow%2FtermsAndConditions%3Futm_campaign%3D549%253A148723%253A79235%26utm_medium%3Dmail%26utm_source%3Dmail&data=%7B%22deviceType%22%3A%22WEB%22%2C%22encEmail%22%3A%22552a0a57202a68153d12a5813f4d2a478ce406734eccacdb83140320a90e357f5c6f20e6ee727f90da5a33670e8ae0ea%22%2C%22mailType%22%3A%22fn_recruitment%22%2C%22mailerId%22%3A%22148723%22%2C%22campaignId%22%3A%22549%22%2C%22segmentId%22%3A%2279235%22%2C%22appId%22%3A456%2C%22tenantId%22%3A%221%22%2C%22clickPosition%22%3A4%2C%22eventName%22%3A%22communicationClick%22%2C%22communicationType%22%3A%22mail%22%7D](https://cm.naukri.com/?redirect=https://www.firstnaukri.com/freshersmnj/mynaukri.php/Show/termsAndConditions?utm_campaign%3D549%253A148723%253A79235%26utm_medium%3Dmail%26utm_source%3Dmail&data=%7B%22deviceType%22:%22WEB%22,%22encEmail%22:%22552a0a57202a68153d12a5813f4d2a478ce406734eccacdb83140320a90e357f5c6f20e6ee727f90da5a33670e8ae0ea%22,%22mailType%22:%22fn_recruitment%22,%22mailerId%22:%22148723%22,%22campaignId%22:%22549%22,%22segmentId%22:%2279235%22,%22appId%22:456,%22tenantId%22:%221%22,%22clickPosition%22:4,%22eventName%22:%22communicationClick%22,%22communicationType%22:%22mail%22%7D)

ATS-Friendly Resume: How to Beat Applicant Tracking Systems (2026 Guide) - Naukri.com, [https://www.naukri.com/career-advice/how-to-beat-applicant-tracking-systems](https://www.naukri.com/career-advice/how-to-beat-applicant-tracking-systems)

AI Checking: Complete Guide for Indian Job Seekers (2026) - Naukri.com, [https://www.naukri.com/career-advice/ai-checking-software](https://www.naukri.com/career-advice/ai-checking-software)

Terms of Service - Indeed, [https://www.indeed.com/legal](https://www.indeed.com/legal)

Web Scraping: Definition, Uses And Types Explained | Indeed.com India, [https://in.indeed.com/career-advice/career-development/what-is-web-scraping](https://in.indeed.com/career-advice/career-development/what-is-web-scraping)

Indeed Apply | Indeed Partner Docs, [https://docs.indeed.com/legal-terms/indeed-apply](https://docs.indeed.com/legal-terms/indeed-apply)

AI Use Policy India 2026: Complete Drafting Guide for Companies, [https://siddharthgupta.in/how-to/draft-ai-use-policy-company-india](https://siddharthgupta.in/how-to/draft-ai-use-policy-company-india)

DIGITAL INDIA BHASHINI DIVISION-DIC, [https://www.meity.gov.in/static/uploads/2026/08/70edc74db220f4f06f000c56522456da.pdf](https://www.meity.gov.in/static/uploads/2026/08/70edc74db220f4f06f000c56522456da.pdf)

Draft Regulations for Use of Artificial Intelligence (AI) in Courts, 2026, [https://www.civis.vote/consultations/1575](https://www.civis.vote/consultations/1575)
