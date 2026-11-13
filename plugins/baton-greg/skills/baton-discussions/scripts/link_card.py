"""Inspect a local Baton wake link without opening, executing or trusting it."""
import argparse
import json
import re
import shlex
from urllib.parse import parse_qsl, urlsplit
import uuid

READER='/home/olliver/.local/share/baton-som-links-20261113/baton_discussion_links.py'
KINDS={'question','reply','correction','counterexample','note','decision'}


def chat(value):
    if str(uuid.UUID(value))!=value:
        raise ValueError('noncanonical chat ID')
    return value


def card(link):
    if not isinstance(link,str) or len(link)>2048 or any(ord(c)<32 for c in link):
        raise ValueError('invalid wake link')
    u=urlsplit(link)
    if u.scheme!='baton' or u.netloc!='local' or u.fragment:
        raise ValueError('only local Baton post links are supported')
    parts=u.path.split('/')
    if len(parts)!=5 or parts[1]!='t' or parts[3]!='p':
        raise ValueError('invalid topic/post route')
    topic=parts[2]
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,63}',topic):
        raise ValueError('invalid topic')
    post=chat(parts[4]);pairs=parse_qsl(u.query,keep_blank_values=True,strict_parsing=True);q=dict(pairs)
    if len(q)!=len(pairs) or set(q)!={'v','kind','from','to','topic','until','sort'}:
        raise ValueError('invalid or repeated metadata')
    if not re.fullmatch(r'[1-9][0-9]{0,8}',q['v']) or q['kind'] not in KINDS or q['sort'] not in ('oldest','newest'):
        raise ValueError('invalid revision/type/sorting')
    chat(q['from'])
    if q['to']!='all':chat(q['to'])
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,63}',q['topic']):
        raise ValueError('invalid topic hint')
    if q['until'] and not re.fullmatch(r'[0-9]{1,12}',q['until']):
        raise ValueError('invalid invitation expiry hint')
    return {'topic_id':topic,'post_id':post,'revision':int(q['v']),
            'untrusted_hints':q,'route_topic_hint_mismatch':q['topic']!=topic,
            'read_argv':['python3',READER,'read',link],
            'shell_read_command':shlex.join(['python3',READER,'read',link]),
            'access_state':'not_checked',
            'meaning':'Local read recipe only. Verify current Greg route and permission; resolve stored data before trusting hints. This does not execute, grant access, wake a model or verify authorship.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('link');a=p.parse_args()
    print(json.dumps(card(a.link),ensure_ascii=True,indent=2))
