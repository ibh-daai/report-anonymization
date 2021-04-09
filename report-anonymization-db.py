import sys, re, psycopg2, psycopg2.extras, warnings, datetime
from striprtf.striprtf import rtf_to_text

prefixesEliminated = ['Name: ','Phys: ','Sex: ','Exam Date: ', 'DOB: ', 'Acct: ', 'Reported By: ','CC: ','Technologist: ',
                      'Cosigner:', 'Unit No: ', 'Radiology No:', 'Signed By Cosigner: ','PAGE 1', 'PAGE 2', 'PAGE 3',
                      'Signed Report', 'Transcribed Date/Time: ', 'Transcriptionist: ', 'Printed Date/Time: ',
                      #'Comparison',
                      'Date/Time: ','EXAM#','TYPE/EXAM','CHEST:','Chest x-ray 2 views:','-------------','************',
                      'Report electronically signed', '** REPORT ELECTRONICALLY SIGNED',
                      'If you have received this report in error, please return by Fax to',
                      'Health Information Management at Trillium Health Partners at','905-848-7677.',
                      'If you don\'t have access to fax, or have other','questions, please call 905-848-7580 ext. 2172.',
                      '** REPORT SIGNED IN OTHER VENDOR SYSTEM', 'If you have received this report in error',
                      'This report was electronically dictated by',
                      # CLIC blurbs
                      'activated for this case in order to notify the healthcare team caring',
                      'for this patient. Confirmation of receipt of the important findings',
                      'will be documented in PACS.',
                      'initiated to notify the health care team caring for this patient of',
                      'initiated to notify the health care team caring for this patient.',
                      'initiated to notify the health care team caring for this patient, as',
                      'there was either no Physician clinical impression or the clinical',
                      'impression does not correlate with the radiologist impression. Receipt',
                      'of this report will be documented in PACS.',
                      'results that require attention. Receipt of this report will be',
                      'Receipt of this report will be documented in PACS.','documented in PACS.',
                      '*     ATTENTION', # ATTENTION PHYSICIAN, ATTENTION ORDERING PHYSICIAN or ATTENTION EMERGECY PHYSICIAN - This is one half of a "critical finding" warning, the other half is matched and redacted approperiately in redactActionableFinding()
                      '*                ATTENTION',
                      'Medical Imaging Resident'
                      ]

relativeDateRefernces = ['same\\W(day|week)', 'the (day|week)', 'prior\\W(day|week)', 'previous\\W(day|week)', 'yesterday', '[0-9]{1}\\W(day|week)(s|)', '(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\\W(day|week)(s|)', 'few (day|week)s', '(day|week)(s|) prior', 'day\\W[0-9]{1,}', 'last week']

# Don't bother with the future warnings about regular expressions
warnings.simplefilter(action='ignore', category=FutureWarning)

def startsWithAny(str, prefixes):
    for prefix in prefixes:
        if str.startswith(prefix):
            return True
    return False

def redactDateAndTime(str):
    # Part 1: match time formats
    str = re.sub("[0-9]{1,2}:[0-9]{2}\\W(AM|PM|am|pm|a.m.|p.m.)", "[REDACTED TIME]", str)  # E.g. 7:21pm
    str = re.sub("(^|\\s).* at .* hrs", " [REDACTED TIME]", str)
    str = re.sub("[0-9]{1,2}(\\W|)[0-9]{2}\\W([0-9]{2}\\W|)(hours|hrs)", "[REDACTED TIME]", str)  # E.g. 1012 hours

    # Part 2: Match different date formats
    # Note: I am using \W to match white spaces, instead of just a whitespace or \s, because some of these reports are using 0xa0 for space instead of the usual 0x20, and \s doesn't seem to detect the two variants correctly. Sigh!
    str = re.sub("[A-Z]{1}[a-z]{1,}\\W[0-9]{1,2}(,|)\\W[0-9]{2,4}", "[REDACTED DATE]", str)  # E.g. May 21, 2020
    str = re.sub("[[0-9]{1,2}\\W[A-Z]{1}[a-z]{1,}(,|)\\W[0-9]{2,4}", "[REDACTED DATE]", str)  # E.g. 21 May 2020
    str = re.sub("[[0-9]{1,2}(\\W|-|/)[A-Z]{1}[a-z]{2,}(\\W|-|/)[0-9]{2,4}", "[REDACTED DATE]", str)  # E.g. 21-May-2020 or 21/May/2020 or 21 May 2020
    str = re.sub("[[0-9]{1,4}(\\.|-|/)[0-9]{1,2}(\\.|-|/)[0-9]{1,4}", "[REDACTED DATE]",str)  # E.g. 5/11/16, 5.11.16, 5-11-2016 or 2016-05-11

    # Note, the following two lines should execute AFTER the above lines, to avoid a partial date matching
    str = re.sub("[A-Z]{1}[a-z]{1,}(,|)\\W[0-9]{2,4}", "[REDACTED DATE]", str)  # E.g. May 2020 or May, 2020
    str = re.sub("20[0-9]{2}", "[REDACTED DATE]", str)  # E.g. 2016 (ie just a year)
    str = re.sub("[A-Z]{1}[a-z]{1,}\\W[0-9]{1,2}", "[REDACTED DATE]", str)  # E.g. May 21
    str = re.sub("(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\\W[0-9]{1,2}", "[REDACTED DATE]", str)  # E.g. May 21 - expressing months explicitly to avoid matching measurements (E.g. Approximaly 5 mm)
    str = re.sub("(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)(\\W|$)","[REDACTED DATE]",str)  # Just a month

    # Part 3: Relative date references (e.g. yesterday)
    for ref in relativeDateRefernces:
        str = re.sub(ref, "[REDACTED TIME]", str, flags=re.IGNORECASE)

    return str

def redactActionableFinding(str):
    redaction = "[CRITICAL FINDING]";
    str = str.replace("The THP Actionable Findings process has been initiated to notify the health care team caring for this patient of results that require attention. Receipt of this report will be documented in the HIS", redaction)
    str = str.replace("The THP Actionable Findings process has been initiated", redaction) # For some reports where the text wrapping is hard-coded
    str = str.replace("THP CLIC (Closing the Loop on Important Communications) process initiated to notify the health care team caring for this patient of results that require attention. Receipt of this report will be documented in PACS.", redaction)
    str = str.replace("THP CLIC (Closing the Loop on Important Communications) process is initiated to notify the health care team caring for this patient of results that require attention. Receipt of this report will be documented in PACS.", redaction)
    str = str.replace("THP CLIC (Closing the Loop on Important Communications) process", redaction) # For some reports where the text wrapping is hard-coded
    str = str.replace("THP CLIC", redaction)  # Catch-all for random versions that have words misspelled and/or extra spaces. Sigh!
    str = str.replace("THE ABOVE FINDING MAY REQUIRE FOLLOW UP",redaction)
    str = str.replace("THE ABOVE FINDING REQUIRES FOLLOW UP", redaction)
    str = str.replace("**ATTENTION PHYSICIAN, FOLLOW UP IS REQUIRED**", redaction)
    str = str.replace("**ATTENTION PHYSICIAN, FOLLOW UP MAY BE REQUIRED**", redaction)
    return str


def anonymizeReport(report):
    lines = report.splitlines()
    reportNew = ""
    for line in lines:
        # Trim white space at the start & end of the line
        line = line.strip()

        if startsWithAny(line,prefixesEliminated):
            line = ''

        # redact potential patient names
        line = re.sub('(Mr|Ms|Mrs)(\\.|)\\W[\\w]{2,}\\W', "[REDACTED NAME]", line)

        # redact accession numbers
        line = re.sub('(E|)[0-9]{5,}(|[A-Z]]{2})', "[REDACTED ACCESSION]", line)

        # redact references to medical residents
        line = re.sub('(\\(|)PGY(\\s|)[0-9](\\>|).*Medical Imaging Resident', "[REDACTED RESIDENT]", line)

        # detect and remove any dates (might be a reference to a comparison prior study
        line = redactDateAndTime(line)

        # detect and remove any mentions of critical findings
        line = redactActionableFinding(line)

        # separate from the if/else above
        line = line.strip()
        if line:
            reportNew += line + '\n'

    return reportNew;

if __name__ == '__main__':
    # Connect to PG SQL
    connect = "host='pgserver' dbname='pgdb' user='pguser' password='pgpassword' client_encoding='UTF8'"
    pgconn = psycopg2.connect(connect)
    pgconn.autocommit = True
    pgsql = pgconn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    pgsql.execute("SELECT original_study_id, report_text FROM public.original_study WHERE temp_anon_report IS NULL limit 100000;")
    # use the statements below to target specific types of reports for testing
    #pgsql.execute("select * from original_study where report_text ILIKE '%PGY.%' OR report_text ILIKE '%resident%';")
    #pgsql.execute("select * from original_study where report_text LIKE '{\\\\rtf1%' order by random() limit 25;")
    #pgsql.execute("SELECT * FROM original_study where original_study_id=12345;")
    rows = pgsql.fetchall()
    total = len(rows)
    i = 0;
    print(datetime.datetime.now())

    for row in rows:
        i += 1
        if ((i % 1000) == 0):
            print("%.2f percent complete" % (i * 100 / total))

        id = row['original_study_id']
        report = row['report_text']
        if (report.startswith('{\\rtf1')): # RTF report, must be converted to plain text
            #print(str(row['original_study_id']) + " --- RTF --------------------------------")
            report = rtf_to_text(report)
        #else:
            #print(str(row['original_study_id']) + " --- text --------------------------------")

        #print(report) # Before
        #print("=====================================")

        report = anonymizeReport(report)

        #print(report) #After
        #print("\n\n")

        pgsql.execute("UPDATE original_study SET temp_anon_report=(%s) WHERE original_study_id=(%s)", (report, str(id)))

    print(datetime.datetime.now())
