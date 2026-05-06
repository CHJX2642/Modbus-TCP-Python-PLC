"""
Flask Web 服务模块
提供实时数据采集状态的 Web API
通过 API 接口向前端提供数据，前端定时轮询
"""

from flask import Flask, jsonify                               # 导入 Flask 核心组件
from shared_state import state                                 # 导入共享状态单例

app = Flask(__name__)                                          # 创建 Flask 应用实例


@app.route("/api/status")                                      # 定义状态 API 路由
def api_status():
    """
    返回实时状态 JSON 数据，供前端轮询

    返回格式：
    {
        "values": {"变量键": 值, ...},
        "system": {"plc_connected": bool, "last_update": str, ...}
    }
    """
    return jsonify(state.get_all())                            # 获取全部状态并转为 JSON 返回


if __name__ == "__main__":                                     # 直接运行此文件时
    app.run(host="0.0.0.0", port=5000,                         # 启动 Flask 服务
            debug=False, threaded=True)                        # 关闭调试模式，开启多线程
