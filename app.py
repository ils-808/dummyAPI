from fastapi import FastAPI, HTTPException, Path, Request, status, APIRouter
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi_sqlalchemy import DBSessionMiddleware, db
from sqlalchemy import Column, String, DateTime, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from pydantic import BaseModel, Field
from datetime import datetime
import uuid
from faker import Faker

# Инициализация приложения
app = FastAPI(title="Multi-user Buggy API", version="1.0", description="API with intentional bugs", redoc_url=None)
router = APIRouter()
faker = Faker()

# Настройки базы данных
DATABASE_URL = "sqlite:///./users.db"
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


# Переопределеяем код ошибки, чтобы вместо 422 возвращалась 500ая при неправильной валидации
# Bug: Returns 500 instead of 400
async def custom_exception_handler(request: Request, exc: RequestValidationError):
    if request.url.path.endswith("/users") and request.method == "POST":
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
@app.get("/", include_in_schema=False)
def root():
    """Root endpoint to display a custom message"""
    return {"message": "Welcome to the Multi-user Buggy API! Use /docs for Swagger documentation."}


@app.post("/init", response_model=dict, summary="Initialize a new namespace with prepopulated users")
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
        db.session.commit()
    return {"namespace": namespace}


@app.get("/{namespace}/users", response_model=list[UserResponse], summary="List users in the namespace")
def list_users(namespace: str):
    """List users in the namespace"""
    with db():
        users = db.session.query(User).filter_by(namespace=namespace).all()
    # Bug: Return outdated data (users created during the session may not appear)
    users = users[:-1]  # Возвращаем только часть пользователей
    if not users:
        raise HTTPException(status_code=404, detail="Namespace not found")
    return users


@app.post("/{namespace}/users", response_model=UserResponse, summary="Create a new user")
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


@app.get("/{namespace}/users/{user_id}", response_model=UserResponse, summary="Get a single user")
def get_user(namespace: str, user_id: str = Path(..., description="User ID")):
    """Get a single user"""
    with db():
        user = db.session.query(User).filter_by(namespace=namespace, id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.put("/{namespace}/users/{user_id}", response_model=UserResponse, summary="Update a user")
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


@app.delete("/{namespace}/users/{user_id}", status_code=204, summary="Delete a user")
def delete_user(namespace: str, user_id: str):
    """Delete a user"""
    with db():
        user = db.session.query(User).filter_by(namespace=namespace, id=user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        db.session.delete(user)
        db.session.commit()
    return None


# Подключение маршрутов и обработчиков
app.include_router(router)

# Установка кастомного обработчика исключений
app.add_exception_handler(RequestValidationError, custom_exception_handler)
