import asyncio

import uvicorn
import uvloop

from kube_admission import log

loop = uvloop.new_event_loop()
asyncio.set_event_loop(loop)


def http_main(app='kube_admission.app:app'):
    uvicorn.run(app, host='0.0.0.0', port=8000,
                log_config=log.configs)
