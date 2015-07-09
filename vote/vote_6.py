#! /usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.append('../')
import re
import json
import codecs
import psycopg2
from datetime import datetime
import db_settings
import ly_common
import vote_common


def SittingDict(text):
    ms = re.search(u'''
        第(?P<ad>[\d]+)屆
        第(?P<session>[\d]+)會期
        第(?P<times>[\d]+)次
        (臨時會第(?P<temptimes>[\d]+)次)?
        (?:會議|全院委員會)
    ''', text, re.X)
    if ms.group('temptimes'):
        uid = '%02d-%02dT%02d-YS-%02d' % (int(ms.group('ad')), int(ms.group('session')), int(ms.group('times')), int(ms.group('temptimes')))
    else:
        uid = '%02d-%02d-YS-%02d' % (int(ms.group('ad')), int(ms.group('session')), int(ms.group('times')))
    return ms, uid

def InsertVote(uid, sitting_id, vote_seq, content):
    match = re.search(u'(?:建請|建請決議|並請|提請|擬請|要求)(?:\S){0,4}(?:院會|本院|\W{1,3}院|\W{1,3}部|\W{1,3}府).*(?:請公決案|敬請公決)', content)
    #c.execute('''
    #    UPDATE vote_vote
    #    SET content = %s, conflict = null
    #    WHERE uid = %s
    #''', (content, uid))
    c.execute('''
        INSERT into vote_vote(uid, sitting_id, vote_seq, content)
        SELECT %s, %s, %s, %s
        WHERE NOT EXISTS (SELECT 1 FROM vote_vote WHERE uid = %s)
    ''', (uid, sitting_id, vote_seq, content, uid))

def GetVoteContent(vote_seq, text):
    l = text.split()
    if re.search(u'附後[（(】。]', l[-2]) or re.search(u'^(其他事項|討論事項)$', l[-2]):
        return l[-1]
    if re.search(u'[：:]$', l[-2]) or re.search(u'(公決|照案|議案)[\S]{0,3}$', l[-2]) or re.search(u'^(決議|決定)[：:]', l[-1]):
        return '\n'.join(l[-2:])
    if re.search(u'[：:]$',l[-3]):
        return '\n'.join(l[-3:])
    i = -3
    # 法條修正提案列表類
    if ly_common.GetLegislatorId(c, l[-2]) or ly_common.GetLegislatorId(c, l[-3]) or re.search(u'(案|審查)[\S]{0,3}$', l[-2]):
        while not re.search(u'(通過|附表|如下|討論)[\S]{1,2}$', l[i]):
            i -= 1
        return '\n'.join(l[i:])
    # 剩下的先向上找上一個附後，找兩附後之間以冒號作結，如找不到
    if vote_seq != '001':
        while not re.search(u'附後[（(】。]', l[i]):
            i -= 1
        for line in reversed(range(i-1,-3)):
            if re.search(u'[：:]$', l[line]):
                return '\n'.join(l[line:])
        return '\n'.join(l[i+1:])
    # 最後方法
    if re.search(u'^[\S]{1,5}在場委員', l[-1]):
        return '\n'.join(l[-2:])
    else:
        return l[-1]
    print 'WTF'
    print text
    raw_input()

def MakeVoteRelation(legislator_id, vote_id, decision):
    c.execute('''
        UPDATE vote_legislator_vote
        SET decision = %s, conflict = null
        WHERE legislator_id = %s AND vote_id = %s
    ''', (decision, legislator_id, vote_id))
    c.execute('''
        INSERT into vote_legislator_vote(legislator_id, vote_id, decision)
        SELECT %s, %s, %s
        WHERE NOT EXISTS (SELECT 1 FROM vote_legislator_vote WHERE legislator_id = %s AND vote_id = %s)
    ''',(legislator_id, vote_id, decision, legislator_id, vote_id))

def LiterateVoter(sitting_dict, text, vote_id, decision):
    firstName = ''
    for name in text.split():
        #--> 兩個字的立委中文名字中間有空白
        if len(name) < 2 and firstName == '':
            firstName = name
            continue
        if len(name) < 2 and firstName != '':
            name = firstName + name
            firstName = ''
        #<--
        legislator_id = ly_common.GetLegislatorId(c, name)
        if legislator_id:
            legislator_id = ly_common.GetLegislatorDetailId(c, legislator_id, sitting_dict["ad"])
            MakeVoteRelation(legislator_id, vote_id, decision)
        else:
            break

def IterEachDecision(votertext, sitting_dict, vote_id):
    mapprove, mreject, mquit = re.search(u'[\s、]贊成[\S]*?者[:：][\d]+人', votertext), re.search(u'[\s、]反對[\S]*?者[:：][\d]+人', votertext), re.search(u'[\s、]棄權者[:：][\d]+人', votertext)
    if not mapprove:
        print u'==找不到贊成者==\n', votertext
        raw_input()
    else:
        LiterateVoter(sitting_dict, votertext[mapprove.end():], vote_id, 1)
    if not mreject:
        print u'==找不到反對者==\n', votertext
        raw_input()
    else:
        LiterateVoter(sitting_dict, votertext[mreject.end():], vote_id, -1)
    if not mquit:
        print u'==找不到棄權者==\n', votertext
    else:
        LiterateVoter(sitting_dict, votertext[mquit.end():], vote_id, 0)
    return mapprove, mreject, mquit

def IterVote(text, sitting_dict):
    sitting_id = sitting_dict["uid"]
    print sitting_id
    match, vote_id, vote_seq = None, None, 0
    # For veto or no-confidence voting
    mvoter = re.search(u'記名投票表決結果[:：]', text)
    if mvoter:
        print u'有特殊表決!!\n'
        votertext = text[mvoter.end():]
        vote_seq = '%03d' % (vote_seq+1)
        vote_id = '%s-%s' % (sitting_id, vote_seq)
        content = GetVoteContent(vote_seq, text[:mvoter.start()])
        if content:
            InsertVote(vote_id, sitting_id, vote_seq, content)
        if vote_id:
            mapprove, mreject, mquit = IterEachDecision(votertext, sitting_dict, vote_id)
    # For normal voting
    mvoter = re.search(u'記名表決結果名單[:：]', text)
    if mvoter:
        votertext = text[mvoter.end():]
        anchors = []
        for match in re.finditer(u'附後[（(]?[一二三四五六七八九十】。]+', text):
            anchor = match.group()
            if anchor in anchors:
                continue
            anchors.append(anchor)
            vote_seq = '%03d' % (int(vote_seq)+1)
            vote_id = '%s-%s' % (sitting_id, vote_seq)
            content = GetVoteContent(vote_seq, text[:match.start()+2])
            print content
            #raw_input()
            if content:
                InsertVote(vote_id, sitting_id, vote_seq, content)
            if vote_id:
                mapprove, mreject, mquit = IterEachDecision(votertext, sitting_dict, vote_id)
            votertext = votertext[(mquit or mreject or mapprove).end():]
        if not match:
            print u'有記名表決結果名單無附後'
    else:
        print u'無記名表決結果名單'

conn = db_settings.con()
c = conn.cursor()
ad = 6
dicts = json.load(open('minutes.json'))
for meeting in dicts:
    print meeting['name']
    sourcetext = codecs.open(u'meeting_minutes/%s.txt' % meeting['name'], 'r', 'utf-8').read()
    ms, uid = SittingDict(meeting['name'])
    if int(ms.group('ad')) != ad:
        continue
    date = ly_common.GetDate(sourcetext)
    if not date: # no content
        continue
    sitting_dict = {"uid": uid, "name": meeting['name'], "ad": ms.group('ad'), "date": date, "session": ms.group('session'), "links": meeting['links']}
    ly_common.InsertSitting(c, sitting_dict)
    ly_common.FileLog(c, meeting['name'])
    ly_common.Attendance(c, sitting_dict, sourcetext, u'出席委員[:：]?', 'YS', 'present')
    ly_common.Attendance(c, sitting_dict, sourcetext, u'請假委員[:：]?', 'YS', 'absent')
    IterVote(sourcetext, sitting_dict)

vote_common.conscience_vote(c, ad)
vote_common.not_voting_and_results(c)
vote_common.vote_param(c)
vote_common.attendance_param(c)
conn.commit()
