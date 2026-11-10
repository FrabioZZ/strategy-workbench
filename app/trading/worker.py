import threading
from app.store import now

class PaperWorker:
    def __init__(self,service):
        self.service=service
        self.stop=threading.Event()
        self.thread=threading.Thread(target=self.run,name='local-paper-daily',daemon=True)
        self.thread.start()

    def tick(self):
        store=self.service.store
        with store.transaction() as c:
            ids=[v['id'] for v in store.list(c,'paper') if v['status']=='running']
        for ident in ids:
            if self.stop.is_set(): break
            try:
                with store.transaction() as c:
                    if store.get(c,'paper',ident)['status']=='running': self.service.action(c,ident,'sync')
            except Exception:
                # Transaction rolled back; persist visible failure without echoing provider secrets.
                with store.transaction() as c:
                    value=store.get(c,'paper',ident)
                    value.update(feed_status='error',message='行情同步失败，账本未推进；请检查数据或重新创建会话',heartbeat_at=now())
                    store.put(c,'paper',value)

    def run(self):
        while not self.stop.wait(15):
            self.tick()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=25)
