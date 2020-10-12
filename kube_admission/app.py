import abc
import base64
import copy
import logging

import jsonpatch
from starlette.applications import Starlette
from starlette.endpoints import HTTPEndpoint
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse as StarletteJsonResponse
from starlette.responses import PlainTextResponse

logger = logging.getLogger(__name__)

# https://kubernetes.io/zh/docs/reference/access-authn-authz/extensible-admission-controllers/


app = Starlette(debug=True)

NotDefined = '<NotDefined/>'


class AdmissionReview:

    def __init__(self, data: dict):
        self.data = data
        self.api_version = data['apiVersion']
        self.kind = data['kind']

        self.request = data['request']

        self.uid = self.request['uid']
        self.request_uid = self.request['uid']

        self.request_object = self.request['object']
        self.request_old_object = self.request['oldObject']

    def get_value_by_path(self, key, *paths, default=NotDefined, _target=None):
        target = _target or self.data
        target = target.get(key, default)
        return self.get_value_by_path(*paths, default=default, _target=target) if paths else target


class AdmissionReviewRequest(StarletteRequest):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.admission = None

    async def dispatch_admission_arguments(self):
        """
        {
          "apiVersion": "admission.k8s.io/v1",
          "kind": "AdmissionReview",
          "request": {
            # 唯一标识此准入回调的随机 uid
            "uid": "705ab4f5-6393-11e8-b7cc-42010a800002",

            # 传入完全正确的 group/version/kind 对象
            "kind": {"group":"autoscaling","version":"v1","kind":"Scale"},
            # 修改 resource 的完全正确的的 group/version/kind
            "resource": {"group":"apps","version":"v1","resource":"deployments"},
            # subResource（如果请求是针对 subResource 的）
            "subResource": "scale",

            # 在对 API 服务器的原始请求中，传入对象的标准 group/version/kind
            # 仅当 webhook 指定 `matchPolicy: Equivalent` 且将对 API 服务器的原始请求转换为 webhook 注册的版本时，这才与 `kind` 不同。
            "requestKind": {"group":"autoscaling","version":"v1","kind":"Scale"},
            # 在对 API 服务器的原始请求中正在修改的资源的标准 group/version/kind
            # 仅当 webhook 指定了 `matchPolicy：Equivalent` 并且将对 API 服务器的原始请求转换为 webhook 注册的版本时，这才与 `resource` 不同。
            "requestResource": {"group":"apps","version":"v1","resource":"deployments"},
            # subResource（如果请求是针对 subResource 的）
            # 仅当 webhook 指定了 `matchPolicy：Equivalent` 并且将对 API 服务器的原始请求转换为该 webhook 注册的版本时，这才与 `subResource` 不同。
            "requestSubResource": "scale",

            # 被修改资源的名称
            "name": "my-deployment",
            # 如果资源是属于命名空间（或者是命名空间对象），则这是被修改的资源的命名空间
            "namespace": "my-namespace",

            # 操作可以是 CREATE、UPDATE、DELETE 或 CONNECT
            "operation": "UPDATE",

            "userInfo": {
              # 向 API 服务器发出请求的经过身份验证的用户的用户名
              "username": "admin",
              # 向 API 服务器发出请求的经过身份验证的用户的 UID
              "uid": "014fbff9a07c",
              # 向 API 服务器发出请求的经过身份验证的用户的组成员身份
              "groups": ["system:authenticated","my-admin-group"],
              # 向 API 服务器发出请求的用户相关的任意附加信息
              # 该字段由 API 服务器身份验证层填充，并且如果 webhook 执行了任何 SubjectAccessReview 检查，则应将其包括在内。
              "extra": {
                "some-key":["some-value1", "some-value2"]
              }
            },

            # object 是被接纳的新对象。
            # 对于 DELETE 操作，它为 null。
            "object": {"apiVersion":"autoscaling/v1","kind":"Scale",...},
            # oldObject 是现有对象。
            # 对于 CREATE 和 CONNECT 操作，它为 null。
            "oldObject": {"apiVersion":"autoscaling/v1","kind":"Scale",...},
            # options 包含要接受的操作的选项，例如 meta.k8s.io/v CreateOptions、UpdateOptions 或 DeleteOptions。
            # 对于 CONNECT 操作，它为 null。
            "options": {"apiVersion":"meta.k8s.io/v1","kind":"UpdateOptions",...},

            # dryRun 表示 API 请求正在以 `dryrun` 模式运行，并且将不会保留。
            # 带有副作用的 Webhook 应该避免在 dryRun 为 true 时激活这些副作用。
            # 有关更多详细信息，请参见 http://k8s.io/docs/reference/using-api/api-concepts/#make-a-dry-run-request
            "dryRun": false
          }
        }
        """
        self.admission = AdmissionReview(await self.json())


class AdmissionReviewResponse(StarletteJsonResponse):

    def __init__(self, req=None, *, uid=None, allowed=True, status=None, patch=None, patch_type=None, **kwargs):
        """
        {
          "apiVersion": "admission.k8s.io/v1",
          "kind": "AdmissionReview",
          "response": {
            "uid": "<value from request.uid>",
            "allowed": true
          }
        }
        """
        uid = uid or req.admission.request_uid

        response = {
            "uid": uid,
            "allowed": bool(allowed),
        }

        if status:
            response['status'] = status

        if patch:
            response['patch'] = patch
            response['patchType'] = patch_type

        content = {
            "apiVersion": "admission.k8s.io/v1",
            "kind": "AdmissionReview",
            "response": response
        }

        logger.debug(f'response content: {content}')

        super().__init__(content=content, **kwargs)


class ABCAdmissionReviewView(HTTPEndpoint, metaclass=abc.ABCMeta):
    handlers = (
        {
            'key_path': 'request.dryRun',
            'miss_match_handler': {'func': None, 'action': 'raise'},
            'handlers': {
                True: {'func': 'on_dry_run', 'action': 'response'},
                False: {'func': None, 'action': 'ignore'}
            },
        },

        {
            'key_path': 'request.options.kind',
            'miss_match_handler': {'func': None, 'action': 'raise'},
            'handlers': {
                'CreateOptions': {'func': 'on_create', 'action': 'response'},
                'UpdateOptions': {'func': 'on_update', 'action': 'response'},
                'DeleteOptions': {'func': 'on_delete', 'action': 'response'},
            },
        }
    )

    async def admission_dispatch(self, req):

        for item in self.handlers:

            key_path = item['key_path']
            handlers = item['handlers']
            miss_match_handler = item['miss_match_handler']

            paths = key_path.split('.')
            admission_value = req.admission.get_value_by_path(*paths)

            this_handler = handlers.get(admission_value, miss_match_handler)

            this_action = this_handler['action']
            this_func = this_handler['func']

            if this_action == 'ignore':
                continue
            elif this_action == 'raise':
                ValueError(f'no handler for value {admission_value} for {key_path}')
            elif this_action == 'response':
                try:
                    actual_this_func = getattr(self, this_func)
                    resp = await actual_this_func(req)
                except Exception as e:
                    return await self.on_exception(req, e)
                break
            else:
                raise ValueError(f'unexpected action {this_action} for key {key_path}.')
        else:
            resp = await self.on_miss_match(req)

        if not resp:
            resp = await self.response(req)

        return resp

    async def dispatch(self):
        request = AdmissionReviewRequest(self.scope, receive=self.receive)
        handler_name = "get" if request.method == "HEAD" else request.method.lower()
        await request.dispatch_admission_arguments()
        handler = getattr(self, handler_name, self.method_not_allowed)
        response = await handler(request)
        await response(self.scope, self.receive, self.send)

    @staticmethod
    async def response(*args, **kwargs):
        return AdmissionReviewResponse(*args, **kwargs)

    @staticmethod
    async def deny_response(req, msg):
        return AdmissionReviewResponse(req, allowed=False, status=msg)

    @staticmethod
    async def allow_response(req, msg=None):
        return AdmissionReviewResponse(req, allowed=True, status=msg)

    @staticmethod
    async def patch_response(req, new_req_object, allowed=True):

        paths = ('request', 'object')
        admission_request_object = req.admission.get_value_by_path(*paths)

        diff = jsonpatch.JsonPatch.from_diff(admission_request_object,
                                             new_req_object)
        b64_diff = base64.b64encode(diff.to_string().encode()).decode()

        return AdmissionReviewResponse(patch_type='JSONPatch',
                                       patch=b64_diff,
                                       req=req, allowed=allowed)

    async def patch_status_response(self, req, code=200, allowed=True, error=None, msg=None):

        status = {
            'code': code,
            'e': error,
            'msg': msg,
        }

        paths = ('request', 'object')
        admission_request_object = req.admission.get_value_by_path(*paths)
        new_req_object = copy.deepcopy(admission_request_object)
        new_req_object['status'] = status

        return await self.patch_response(req, new_req_object, allowed=allowed)

    async def patch_exception_status_response(self, req, e, code=500, allowed=True):
        return await self.patch_status_response(
            req, code=code,
            error={
                'msg': str(e),
                'type': str(type(e)),
            },
            allowed=allowed,
        )

    async def on_exception(self, req, error):
        # return await self.patch_exception_status_response(req, error)
        return await self.deny_response(req, f'{str(type(error))}: {str(error)}')

    async def post(self, req):
        return await self.admission_dispatch(req)

    async def on_miss_match(self, _):
        logger.debug('miss match.')

    async def on_dry_run(self, _):
        logger.debug('dry run .')

    async def on_create(self, req):
        raise NotImplemented

    async def on_delete(self, req):
        raise NotImplemented

    async def on_update(self, req):
        raise NotImplemented


@app.route('/health', methods=['GET', ])
class Mutate(HTTPEndpoint):

    @staticmethod
    async def get(_):
        return PlainTextResponse()
