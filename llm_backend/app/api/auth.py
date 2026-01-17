from fastapi import APIRouter, Depends, HTTPException, status
# 删掉了 OAuth2PasswordRequestForm，改回用 Schema
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import create_access_token, get_current_user
from app.schemas.user import UserCreate, UserResponse, Token, UserLogin  # 确保引入了 UserLogin
from app.services.user_service import UserService
from datetime import timedelta
from app.core.config import settings
from app.models.user import User

router = APIRouter()


@router.post("/register", response_model=UserResponse)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    try:
        user_service = UserService(db)
        user = await user_service.create_user(user_data)
        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# 【关键修改】改回 UserLogin (JSON 模式)，以适配前端页面
@router.post("/token", response_model=Token)
async def login(
        user_data: UserLogin,  # <--- 改回这里，接收 JSON
        db: AsyncSession = Depends(get_db)
):
    user_service = UserService(db)

    # 这里的参数名也变回 user_data.email
    user = await user_service.authenticate_user(user_data.email, user_data.password)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/users/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """获取当前登录用户的信息"""
    return current_user