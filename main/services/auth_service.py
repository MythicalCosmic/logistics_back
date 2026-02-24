from typing import Dict, Any, Optional, Tuple
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.db import transaction
from rest_framework_simplejwt.jwt import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
import jwt  

class AuthService:

    @classmethod
    @transaction.atomic
    def register_user(cls, email: str, first_name: str, last_name: str, password: str) -> Dict[str, Any]:
        try:
            #check if email exists first
            email = User.objects.filter(email=email).first()
            if email:
                return {'success': False, 'message': 'Email already exists'}
            
            #check if the fields are empty or too long
            first_name = first_name.strip()
            last_name = last_name.strip()
            if not first_name or not last_name:
                return {'success': False, 'message': 'First name and last name cannot be empty'}
            if len(first_name) > 30 or len(last_name) > 30:
                return {'success': False, 'message': 'First name and last name cannot be longer than 30 characters'}
            
            #check if the password is strong enough
            if len(password) < 8:
                return {'success': False, 'message': 'Password must be at least 8 characters long'}
            
            #lastly create user
            user = User.objects.create_user(
                email=email,
                first_name=first_name,
                last_name=last_name,
                password=password
            )

            user.save()
            #now generate a token for the user

            refresh = RefreshToken.for_user(user)

            return {
                'success':True,
                'message': 'User registered successfully',
                'data': {
                    'refresh': str(refresh),
                    'user_data': {
                        'email': user.email,
                        'first_name': user.first_name,
                        'last_name': user.last_name
                    }
            }} 
        
        except Exception as e:
            return {'success': False, 'message': str(e)}
        

    @classmethod
    @transaction.atomic
    def login(cls, email:str, password: str) -> Dict[str, Any]:
        try:
            #chech email and password exists first and not empty 
            if not email and password:
                return {'success': False, 'message': 'Email and Password fields cannot be empty'}
            
            #check password lenght
            if len(password) < 8:
                return {'success': False, 'message': 'Password lenght must be altleast 8 characters long'}
            
            #check email lenght
            if len(email) < 3:
                return {'success': False, 'message': 'Email is too short'}
            
            #now authenticate 

            user = authenticate(email=email, password=password)

            if user.is_authenticated:
                #generate token here
                token = RefreshToken.for_user(user)
                return {
                    'success': True,
                    'message': 'Logged in successfully',
                    'data': {
                        'token': token,
                        'user_data': {
                            'email': email,
                            'first_name': first_name,
                            'last_name': last_name
                        }
                    }
                }
            #fail side 
            else:
                return {'success': False, 'message': 'Invalid credentials'}

        except Exception as e:
            return {'success': False, 'message': str(e)}


    @classmethod
    @transaction.atomic
    def logout(cls, token: str) -> Dict[str, Any]:
        try:
            #Get the token
            token_obj = Token.objects.get(key=token)
            token_obj.delete()
            return {'success': True, 'message': 'Successfully logged out'}

        except Exception as e:
            return {'success': False, 'message': str(e)}
        
    @classmethod
    @transaction.atomic
    def me(cls, token: str) -> Dict[str, Any]:
        try:
            #get token fist
            user = cls._get_user_from_token(user)
            #check if token is good or not
            if not user:
                return {'success': False, 'message': 'Token is invalid or expired'}

            #return if eveything is good
            return {
                'success': True,
                'message': 'Your data retrived successfully',
                'data': {
                    'email': user.email,
                    'first_name': user.fist_name,
                    'last_name': user.last_name
                }
            }

        except Exception as e:
            return {'success': True, 'message': str(e)}