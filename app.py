import json
from collections import OrderedDict

import uvicorn
from fastapi import FastAPI, HTTPException, Path, Request, status, APIRouter, Depends
from fastapi.responses import JSONResponse
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
import redis.asyncio as redis
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi_sqlalchemy import DBSessionMiddleware, db
from sqlalchemy import Column, String, DateTime, create_engine, Integer, Float
from sqlalchemy.orm import sessionmaker, declarative_base
from pydantic import BaseModel, Field
from datetime import datetime
import uuid
from faker import Faker
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Инициализация приложения
app = FastAPI(redoc_url=None)
# router = APIRouter()
v1_router = FastAPI(tags=["Version 1 (Buggy)"], redoc_url=None)
v2_router = FastAPI(tags=["Version 2 (Fixed)"], redoc_url=None)

faker = Faker()

# Настройки базы данных
DATABASE_URL = "sqlite:///./instance/users.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

app.add_middleware(DBSessionMiddleware, db_url=DATABASE_URL)


# Модель базы данных
class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    namespace = Column(String(36), nullable=False)
    login = Column(String(80), nullable=False)
    created_date = Column(DateTime, default=datetime.now)
    fio = Column(String(120), nullable=True)
    address = Column(String(200), nullable=True)


class Order(Base):
    __tablename__ = "orders"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    namespace = Column(String(36), nullable=False)
    product_name = Column(String(120), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    price = Column(Float, nullable=False, default=0.0)
    created_date = Column(DateTime, default=datetime.now)


Base.metadata.create_all(bind=engine)


# Pydantic модели
class UserCreate(BaseModel):
    login: str = Field(..., description="Unique login")
    fio: str = Field(None, description="Full name")
    address: str = Field(None, description="Address")


class UserResponse(UserCreate):
    id: str
    namespace: str
    created_date: datetime


class OrderCreate(BaseModel):
    product_name: str = Field(..., description="Name of the product")
    quantity: int = Field(..., description="Quantity of the product")
    price: float = Field(..., description="Price per product")


class OrderResponse(OrderCreate):
    id: str
    namespace: str
    created_date: datetime


# Redis URL
REDIS_URL = os.getenv("REDIS_URL", "http://localhost")

# Лимиты запросов
ENABLE_RATE_LIMITER = os.getenv("ENABLE_RATE_LIMITER", False).lower() == 'true'
LIMIT_REQUESTS = int(os.getenv("LIMIT_REQUESTS", 15))
LIMIT_SECONDS = int(os.getenv("LIMIT_SECONDS", 60))


def conditional_rate_limiter():
    return [Depends(RateLimiter(times=LIMIT_REQUESTS, seconds=LIMIT_SECONDS))] if ENABLE_RATE_LIMITER else []


# Инициализация Redis для Rate Limiting
@app.on_event("startup")
async def startup():
    redis_instance = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    await FastAPILimiter.init(redis_instance)


@app.on_event("shutdown")
async def shutdown():
    redis_instance = FastAPILimiter.redis
    await redis_instance.close()


# Переопределеяем код ошибки, чтобы вместо 422 возвращалась 500ая при неправильной валидации
# Bug: Returns 500 instead of 400
async def custom_exception_handler(request: Request, exc: RequestValidationError):
    if 'v1' in request.url.path and request.url.path.endswith("/users") and request.method == "POST":
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=jsonable_encoder({"detail": exc.errors()}),
        )
    else:
        # Для всех остальных случаев возвращаем стандартную обработку
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=jsonable_encoder({"detail": exc.errors()}),
        )


# Эндпоинты API
@app.get("/", include_in_schema=False,
         dependencies=conditional_rate_limiter())
def root():
    """Root endpoint to display a custom message"""
    return {"message": "Welcome to the Multi-user Buggy API! Use /v1/docs and /v2/docs for Swagger documentation."}


@app.head("/", include_in_schema=False,
          dependencies=conditional_rate_limiter())
def root_head():
    """Root endpoint for HEAD requests (monitoring)"""
    return JSONResponse(content={}, status_code=200)


@v1_router.post("/init", response_model=dict, summary="Initialize a new namespace with prepopulated users and orders",
                dependencies=conditional_rate_limiter(), tags=["Init"])
@v2_router.post("/init", response_model=dict, summary="Initialize a new namespace with prepopulated users and orders",
                dependencies=conditional_rate_limiter(), tags=["Init"])
def init_namespace():
    """Initialize a new namespace with prepopulated users"""
    namespace = str(uuid.uuid4())
    with db():
        for _ in range(3):
            user = User(
                namespace=namespace,
                login=faker.unique.user_name(),
                fio=faker.name(),
                address=faker.address(),
            )
            db.session.add(user)
        for _ in range(5):
            order = Order(
                namespace=namespace,
                product_name=faker.word(),
                quantity=faker.random_int(min=1, max=10),
                price=round(faker.random_number(digits=2), 2)
            )
            db.session.add(order)
        db.session.commit()
    return {"namespace": namespace}


@v1_router.get("/{namespace}/users", response_model=list[UserResponse], summary="List users in the namespace",
               dependencies=conditional_rate_limiter(), tags=["User"])
def list_users(namespace: str):
    """List users in the namespace"""
    with db():
        users = db.session.query(User).filter_by(namespace=namespace).all()
    # Bug: Return outdated data (users created during the session may not appear)
    users = users[:-1]  # Возвращаем только часть пользователей
    if not users:
        raise HTTPException(status_code=404, detail="Namespace not found")
    return users


@v2_router.get("/{namespace}/users", response_model=list[UserResponse], summary="List users in the namespace",
               dependencies=conditional_rate_limiter(), tags=["User"])
def list_users(namespace: str):
    """List users in the namespace"""
    with db():
        users = db.session.query(User).filter_by(namespace=namespace).all()
    if not users:
        raise HTTPException(status_code=404, detail="Namespace not found")
    return users


@v1_router.post("/{namespace}/users", response_model=UserResponse, summary="Create a new user",
                dependencies=conditional_rate_limiter(), tags=["User"])
def create_user(namespace: str, user: UserCreate):
    """Create a new user"""
    with db():
        existing_user = db.session.query(User).filter_by(namespace=namespace, login=user.login).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Login must be unique")
        new_user = User(
            namespace=namespace,
            login=user.login,
            fio=user.fio,
            address=user.address,
        )
        db.session.add(new_user)
        db.session.commit()
        db.session.refresh(new_user)
    return new_user


@v2_router.post("/{namespace}/users", response_model=UserResponse, summary="Create a new user",
                dependencies=conditional_rate_limiter(), tags=["User"])
def create_user(namespace: str, user: UserCreate):
    """Create a new user"""
    with db():
        existing_user = db.session.query(User).filter_by(namespace=namespace, login=user.login).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Login must be unique")
        new_user = User(
            namespace=namespace,
            login=user.login,
            fio=user.fio,
            address=user.address,
        )
        db.session.add(new_user)
        db.session.commit()
        db.session.refresh(new_user)
    return new_user


@v1_router.get("/{namespace}/users/{user_id}", response_model=UserResponse, summary="Get a single user",
               dependencies=conditional_rate_limiter(), tags=["User"])
def get_user(namespace: str, user_id: str = Path(..., description="User ID")):
    """Get a single user"""
    with db():
        user = db.session.query(User).filter_by(namespace=namespace, id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user_dict = jsonable_encoder(user)
    # bug: Удаляем id, чтобы создать баг
    user_dict.pop('id', None)

    # Упорядочиваем ключи вручную
    ordered_user_dict = OrderedDict([
        ("login", user_dict.get("login")),
        ("fio", user_dict.get("fio")),
        ("address", user_dict.get("address")),
        ("namespace", user_dict.get("namespace")),
        ("created_date", user_dict.get("created_date"))
    ])

    return JSONResponse(content=ordered_user_dict)


@v2_router.get("/{namespace}/users/{user_id}", response_model=UserResponse, summary="Get a single user",
               dependencies=conditional_rate_limiter(), tags=["User"])
def get_user(namespace: str, user_id: str = Path(..., description="User ID")):
    """Get a single user"""
    with db():
        user = db.session.query(User).filter_by(namespace=namespace, id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@v1_router.put("/{namespace}/users/{user_id}", response_model=UserResponse, summary="Update a user",
               dependencies=conditional_rate_limiter(), tags=["User"])
def update_user(namespace: str, user_id: str, user_update: UserCreate):
    """Update a user"""
    with db():
        user = db.session.query(User).filter_by(namespace=namespace, id=user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        # Bug: no login uniqueness validation
        user.login = user_update.login or user.login
        user.fio = user_update.fio or user.fio
        user.address = user_update.address or user.address
        db.session.commit()
        db.session.refresh(user)
    return user


@v2_router.put("/{namespace}/users/{user_id}", response_model=UserResponse, summary="Update a user",
               dependencies=conditional_rate_limiter(), tags=["User"])
def update_user(namespace: str, user_id: str, user_update: UserCreate):
    """Update a user"""
    with db():
        user = db.session.query(User).filter_by(namespace=namespace, id=user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if user_update.login and user_update.login != user.login:
            existing_user = db.session.query(User).filter_by(namespace=namespace, login=user_update.login).first()
            if existing_user:
                raise HTTPException(status_code=400, detail="Login must be unique")
        user.login = user_update.login or user.login
        user.fio = user_update.fio or user.fio
        user.address = user_update.address or user.address
        db.session.commit()
        db.session.refresh(user)
    return user


@v1_router.delete("/{namespace}/users/{user_id}", status_code=204, summary="Delete a user",
                  dependencies=conditional_rate_limiter(), tags=["User"])
def delete_user(namespace: str, user_id: str):
    """Delete a user"""
    with db():
        user = db.session.query(User).filter_by(namespace=namespace, id=user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        db.session.delete(user)
        # Bug: not saving user deletion
        # db.session.commit()
    return None


@v2_router.delete("/{namespace}/users/{user_id}", status_code=204, summary="Delete a user",
                  dependencies=conditional_rate_limiter(), tags=["User"])
def delete_user(namespace: str, user_id: str):
    """Delete a user"""
    with db():
        user = db.session.query(User).filter_by(namespace=namespace, id=user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        db.session.delete(user)
        db.session.commit()
    return None


# Эндпоинт для получения заказов
@v1_router.get("/{namespace}/orders", response_model=list[OrderResponse], summary="List orders in the namespace",
               dependencies=conditional_rate_limiter(), tags=["Order"])
def list_orders_v1(namespace: str):
    """List orders in the namespace"""
    raise HTTPException(status_code=500, detail="Intentional error for demonstration purposes")


@v2_router.get("/{namespace}/orders", response_model=list[OrderResponse], summary="List orders in the namespace",
               dependencies=conditional_rate_limiter(), tags=["Order"])
def list_orders_v2(namespace: str):
    """List orders in the namespace"""
    with db():
        orders = db.session.query(Order).filter_by(namespace=namespace).all()
    if not orders:
        raise HTTPException(status_code=404, detail="Namespace not found")
    return orders


# Установка кастомного обработчика исключений
v1_router.add_exception_handler(RequestValidationError, custom_exception_handler)

# Подключение маршрутов и обработчиков
app.mount('/v1', v1_router)
app.mount('/v2', v2_router)
app.mount('/latest', v2_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
