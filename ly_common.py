# -*- coding: utf-8 -*-
import re
import codecs
import psycopg2
from datetime import datetime

def FileLog(c, sitting):
    c.execute('''INSERT into legislator_filelog(sitting, date)
            SELECT %s, %s
            WHERE NOT EXISTS (SELECT 1 FROM legislator_filelog WHERE sitting = %s) RETURNING id''', (sitting, datetime.now(), sitting)
    )

def GetDate(text):
    matchTerm = re.search(u'(?P<year>[\d]+)[\s]?年(?P<month>[\d]+)[\s]?月(?P<day>[\d]+)',text)
    if matchTerm:
        return '%04d-%02d-%02d' % (int(matchTerm.group('year'))+1911, int(matchTerm.group('month')), int(matchTerm.group('day')))
    else:
        return None              

def GetLegislatorId(c, name):
    name_like = name + '%'
    c.execute('''SELECT uid FROM legislator_legislator WHERE name like %s''',[name_like])
    r = c.fetchone()
    if r:
        return r[0]

def GetLegislatorIdList(c, text):
    id_list, firstName = [], ''
    for name in text.split():      
        if re.search(u'[）)。】」]$',name):   #立委名字後有標點符號
            name = name[:-1]
        #兩個字的立委中文名字中間有空白
        if len(name)<2 and firstName=='':
            firstName = name
            continue
        if len(name)<2 and firstName!='':
            name = firstName + name
            firstName = ''
        if len(name)>4: #立委名字相連
            name = name[:3]
        legislator_id = GetLegislatorId(c, name)
        if legislator_id:
            id_list.append(legislator_id)
        else:   # return id list if not an legislator name
            return id_list

def AddAttendanceRecord(c, legislator_id, sitting_id, category, status):
    c.execute('''INSERT into legislator_attendance(legislator_id, sitting_id, category, status)
            SELECT %s, %s, %s, %s
            WHERE NOT EXISTS (SELECT 1 FROM legislator_attendance WHERE legislator_id = %s AND sitting_id = %s)''', (legislator_id, sitting_id, category, status, legislator_id, sitting_id)
    )

def Attendance(c, sitting_dict, text, keyword, category, status):
    match = re.search(keyword, text)
    if match:
        for legislator_id in GetLegislatorIdList(c, text[match.end():]):
            AddAttendanceRecord(c, legislator_id, sitting_dict["uid"], category, status)

def InsertSitting(c, sitting_dict):
    complement = {"committee":''}
    complement.update(sitting_dict)
    c.execute('''INSERT into sittings_sittings(uid, name, date, ad, session, committee)
        SELECT %(uid)s, %(name)s, %(date)s, %(ad)s, %(session)s, %(committee)s
        WHERE NOT EXISTS (SELECT 1 FROM sittings_sittings WHERE uid = %(uid)s )''', complement)
