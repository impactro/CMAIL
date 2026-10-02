from datetime import datetime, timedelta, timezone
import pytest
from cmail.extraction import AmbiguousExtraction, find_recent_value, wait_for_recent_value

NOW = datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc)


class Mail:
    def __init__(self, messages, bodies):
        self.items, self.bodies, self.reads = messages, bodies, []

    def messages(self, folder, limit):
        return self.items

    def message(self, folder, identifier):
        self.reads.append(identifier)
        return {'body': self.bodies[identifier]}


def message(identifier, minutes=1, subject='Código de autenticação MFA', sender='login@example.com'):
    return {'id':identifier,'subject':subject,'receivedAt':(NOW-timedelta(minutes=minutes)).isoformat(),
            'from':{'address':sender}}


def find(mail, **kwargs):
    return find_recent_value(mail, subject_contains='codigo de autenticacao',
                             pattern=r'(?<!\d)\d{6}(?!\d)',last_minutes=5,now=NOW,**kwargs)


def test_latest_window_subject_sender_and_leading_zero():
    mail=Mail([message('old',10),message('wrong',subject='Outro'),message('other',sender='other@example.com'),
               message('ok',2)], {'ok':'Código: 014313. Repetição: 014313'})
    result=find(mail,sender='login@example.com')
    assert result.value=='014313'
    assert mail.reads==['ok']
    assert '014313' not in repr(result)


def test_run_start_excludes_previous_run_and_future_dates():
    mail=Mail([message('old',3),message('future',-1)], {})
    assert find(mail,after=NOW-timedelta(minutes=2)) is None
    assert mail.reads==[]


def test_newest_ambiguous_is_not_replaced_by_older_token():
    mail=Mail([message('old',2),message('new',1)],{'old':'123456','new':'123456 ou 654321'})
    with pytest.raises(AmbiguousExtraction):
        find(mail)
    assert mail.reads==['new']


def test_capture_group_and_no_match():
    mail=Mail([message('new')], {'new':'token=abc-123'})
    result=find_recent_value(mail,subject_contains='MFA',pattern=r'token=([\w-]+)',group=1,
                             last_minutes=5,now=NOW)
    assert result.value=='abc-123'
    assert find(mail) is None
    with pytest.raises(ValueError,match='Grupo'):
        find_recent_value(mail,subject_contains='MFA',pattern=r'\d{6}',group=1,
                          last_minutes=5,now=NOW)


def test_poll_30_seconds_and_caller_cancellation(monkeypatch):
    clock=[0]
    monkeypatch.setattr('cmail.extraction.time.monotonic',lambda:clock[0])
    mail=Mail([], {'new':'014313'})
    intervals=[]
    def wait(seconds):
        intervals.append(seconds)
        clock[0]+=seconds
        mail.items=[message('new')]
    query=dict(subject_contains='MFA',pattern=r'\d{6}',last_minutes=10,now=NOW)
    assert wait_for_recent_value(mail,wait=wait,**query).value=='014313'
    assert intervals==[30]
    mail.items=[]
    def cancel(seconds):
        raise RuntimeError('cancelled')
    with pytest.raises(RuntimeError,match='cancelled'):
        wait_for_recent_value(mail,wait=cancel,**query)
