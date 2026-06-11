import json
from plistlib import loads

from fastapi import APIRouter, Depends

from agents.resource_agent import generate_learning_resource
from db import get_conn
from models import LearningResourceGenerateRequest
from utils import success, error, get_current_user

router = APIRouter(prefix="/resources", tags=["resources"])
@router.post("/generate")
def generate_resource_api(request: LearningResourceGenerateRequest, user=Depends(get_current_user)):
    "根据用户输入的课程名和知识点，生成学习资源"
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            select profile_json from student_profiles where user_id = %s
            """,
            (user["id"],)
        )
        row = cursor.fetchone()
        print( row)
        if row is None:
            return error(
                message="当前用户没有学生画像",
                code=400
            )
        else:
            profile = json.loads(row["profile_json"])
            if isinstance(profile,str):
                profile = json.loads(profile)
            resource = generate_learning_resource(
                course_name=request.course_name,
                topic=request.topic,
                profile=profile
            )
            resouce_json = json.dumps(resource,ensure_ascii=False)
            cursor.execute(
                 """
                 insert into learning_resources (
                 user_id,course_name,topic,resource_type,title,content,resource_json
                 )values (%s,%s,%s,%s,%s,%s,%s)
                 """,
                (user["id"],request.course_name,request.topic,resource["resource_type"],resource["title"],resource["content"],resouce_json)
            )
            resource["id"] = cursor.lastrowid
            cursor.execute(
                 """
                 insert into operation_logs
                     (user_id,action,target_type,target_id,detail)
                     values(%s,%s,%s,%s,%s)
                 """,
                (user["id"],
                 "A3_GENERATE_LEARNING_RESOURCE",
                 "learning_resource",
                 resource["id"],

                 json.dumps(
                      {
                          "source": "a3_resource_agent",
                          "course_name": request.course_name,
                          "topic": request.topic,
                          "resource_id": resource["id"],
                          "title": resource["title"],
                          "resource_type": resource["resource_type"]
                      },
                      ensure_ascii=False
                 )
                 )
            )
            conn.commit()

            return success(
                data=resource,
                message="生成学习资源成功"
            )
    except ValueError as e:
        return error(
            message=str(e),
            code = 400
        )
    except Exception as e:
        return error(
            message=f"生成学习资源失败:{str(e)}",
            code = 500
        )
    finally:
        cursor.close()
        conn.close()
@router.get("")
def get_resources(
        page:int = 1,
        size:int = 10,
        user=Depends(get_current_user)
):
    if page <= 0 or size <= 0:
        return error(
            message="page和size必须大于0",
            code=400
        )
    if size > 100:
        return error(
            message="size不能大于100",
            code=400
        )
    "获取当前用户所有的学习资源"
    conn = get_conn()
    cursor = conn.cursor()
    try:
        offset = (page - 1) * size
        cursor.execute(
            """
            select count(*) as total from learning_resources where user_id = %s
            """,
            (user["id"],)
        )
        row = cursor.fetchone()
        print(row)
        total = row["total"]

        cursor.execute(
            """
            select id, user_id, course_name, topic, resource_type, title, created_at
            from learning_resources where user_id = %s order by id desc limit %s offset %s
            """,
            (user["id"],size,offset)
        )
        items = cursor.fetchall()
        return success(
            data={
                "total":total,
                "list":items,
                "page":page,
                "size":size
            },
            message="获取学习资源成功"
        )
    except Exception as e:
        return error(
            message=f"获取学习资源失败:{str(e)}",
            code = 500
        )
    finally:
        cursor.close()
        conn.close()
@router.get("/{resource_id}")
def get_resource_detail(resource_id:int,user = Depends(get_current_user)):
    "查询当前用户某一条学习任务详情"
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            select id,user_id,course_name,topic,resource_type,title,content,
            resource_json,created_at from learning_resources where id = %s
                and user_id = %s
            """,
            (resource_id,user["id"])
        )
        row = cursor.fetchone()
        if row is None:
            return error(
                message="该学习资源不存在",
                code=400
            )
        resource = json.loads(row["resource_json"])
        if isinstance(resource,str):
            resource = json.loads(resource)
        return success(
            data={
                "id":row["id"],
                "user_id":row["user_id"],
                "course_name":row["course_name"],
                "topic":row["topic"],
                "resource_type":row["resource_type"],
                "title":row["title"],
                "content":row["content"],
                "resource":resource,
                "created_at":row["created_at"]
            },
            message="获取学习资源详情成功"
        )
    except Exception as e:
        return error(
            message=f"获取学习资源详情失败:{str(e)}",
            code = 500
        )
    finally:
        cursor.close()
        conn.close()
