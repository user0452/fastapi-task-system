import argparse
import asyncio
import json
import math
from statistics import mean
from time import perf_counter

import httpx


def percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * ratio) - 1)
    return ordered[index]


async def verify(base_url: str, username: str, password: str) -> dict:
    limits = httpx.Limits(max_connections=30, max_keepalive_connections=20)
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=30,
        limits=limits,
        trust_env=False,
    ) as client:
        login = await client.post(
            "/users/login",
            json={"username": username, "password": password},
        )
        login.raise_for_status()
        token = login.json()["data"]["token"]
        headers = {"Authorization": f"Bearer {token}"}
        current_course = await client.get("/api/v1/courses/current", headers=headers)
        current_course.raise_for_status()
        course_id = current_course.json()["data"]["id"]

        async def timed_current_course() -> float:
            started = perf_counter()
            response = await client.get("/api/v1/courses/current", headers=headers)
            response.raise_for_status()
            return perf_counter() - started

        non_ai_latencies = await asyncio.gather(*(timed_current_course() for _ in range(20)))

        async def streamed_chat(index: int) -> dict:
            started = perf_counter()
            first_event = None
            event_types = []
            result_payload = {}
            async with client.stream(
                "POST",
                "/api/v1/agent/chat/stream",
                headers=headers,
                json={
                    "message": "今天学什么？",
                    "course_id": course_id,
                    "current_time": f"2026-07-12 10:{index:02d} UTC+08:00",
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if first_event is None:
                        first_event = perf_counter() - started
                    event = json.loads(line)
                    event_types.append(event["type"])
                    if event["type"] == "result":
                        result_payload = event.get("data") or {}
            return {
                "first_event_seconds": first_event,
                "total_seconds": perf_counter() - started,
                "event_types": event_types,
                "course_id": (result_payload.get("course") or {}).get("id"),
                "run_id": result_payload.get("run_id"),
            }

        streams = await asyncio.gather(*(streamed_chat(index) for index in range(10)))
        final_check = await client.get(
            f"/api/v1/agent/courses/{course_id}/workspace",
            headers=headers,
        )
        final_check.raise_for_status()

    report = {
        "non_ai_requests": 20,
        "non_ai_p95_ms": round(percentile(non_ai_latencies, 0.95) * 1000, 2),
        "non_ai_average_ms": round(mean(non_ai_latencies) * 1000, 2),
        "stream_concurrency": 10,
        "stream_first_event_max_ms": round(
            max(item["first_event_seconds"] for item in streams) * 1000,
            2,
        ),
        "stream_total_max_ms": round(max(item["total_seconds"] for item in streams) * 1000, 2),
        "all_streams_completed": all("done" in item["event_types"] for item in streams),
        "all_streams_course_scoped": all(item["course_id"] == course_id for item in streams),
        "unique_agent_runs": len({item["run_id"] for item in streams if item["run_id"]}),
        "database_pool_healthy_after_streams": final_check.status_code == 200,
    }
    if report["non_ai_p95_ms"] >= 500:
        raise RuntimeError(f"非 AI 接口 P95 超标：{report['non_ai_p95_ms']}ms")
    if report["stream_first_event_max_ms"] >= 1000:
        raise RuntimeError(f"流式首事件超标：{report['stream_first_event_max_ms']}ms")
    if (
        not report["all_streams_completed"]
        or not report["all_streams_course_scoped"]
        or report["unique_agent_runs"] != report["stream_concurrency"]
        or not report["database_pool_healthy_after_streams"]
    ):
        raise RuntimeError("课程并发流未全部完成、发生跨课程结果或连接池未恢复")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="验证 A3 本地性能指标")
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--username", default="a3_demo")
    parser.add_argument("--password", default="A3Demo123!")
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(verify(args.base_url, args.username, args.password)),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
