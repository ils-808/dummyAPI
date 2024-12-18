from flask import Flask, request
from flask_restx import Api, Resource, fields
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid
from faker import Faker

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['RESTX_MASK_SWAGGER'] = False

faker = Faker()
db = SQLAlchemy(app)
api = Api(app, title="Multi-user Buggy API", version="1.0", description="API with intentional bugs", mask=False)


# User model for database
class User(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    namespace = db.Column(db.String(36), nullable=False)
    login = db.Column(db.String(80), nullable=False)
    created_date = db.Column(db.DateTime, default=datetime.now())
    fio = db.Column(db.String(120), nullable=True)
    address = db.Column(db.String(200), nullable=True)

    # def to_dict(self):
    #     return {
    #         "id": self.id,
    #         "namespace": self.namespace,
    #         "login": self.login,
    #         "created_date": self.created_date.isoformat(),
    #         "fio": self.fio,
    #         "address": self.address
    #     }


# API Models
user_model = api.model('User', {
    'login': fields.String(required=True, description="Unique login"),
    'fio': fields.String(description="Full name"),
    'address': fields.String(description="Address")
})

user_response_model = api.model('UserResponse', {
    'id': fields.String(description="User ID"),
    'namespace': fields.String(description="Namespace"),
    'login': fields.String(description="Unique login"),
    'created_date': fields.String(description="Creation date"),
    'fio': fields.String(description="Full name"),
    'address': fields.String(description="Address")
})


# Initialize DB
# db.create_all()

@api.route('/init')
class InitNamespace(Resource):
    def get(self):
        """Initialize a new namespace with prepopulated users"""
        namespace = str(uuid.uuid4())
        for _ in range(3):
            user = User(
                namespace=namespace,
                login=faker.unique.user_name(),
                fio=faker.name(),
                address=faker.address()
            )
            db.session.add(user)
        db.session.commit()
        return {"namespace": namespace}, 200


@api.route('/<namespace>/users')
class Users(Resource):
    @api.marshal_list_with(user_response_model)
    def get(self, namespace):
        """List users in the namespace"""
        users = User.query.filter_by(namespace=namespace).all()
        # Bug: Return outdated data (users created during the session may not appear)
        return users[:-1], 200

    @api.expect(user_model, validate=False)
    @api.marshal_with(user_response_model)
    @api.response(201, "User created", user_response_model)
    @api.response(400, "Login is required")
    def post(self, namespace):
        """Create a new user"""
        data = request.json

        login = data.get('login')
        fio = data.get('fio')
        address = data.get('address')

        if not login:
            # Bug: Returns 500 instead of 400
            return {"error": "Login is required"}, 500

        # Check for login uniqueness within the same namespace
        existing_user = User.query.filter_by(namespace=namespace, login=login).first()
        if existing_user:
            return {"error": "Login must be unique"}, 400

        user = User(namespace=namespace, login=login, fio=fio, address=address)
        db.session.add(user)
        db.session.commit()

        return user, 201


@api.route('/<namespace>/users/<user_id>')
class UserResource(Resource):
    @api.marshal_with(user_response_model)
    def get(self, namespace, user_id):
        """Get a single user"""
        user = User.query.filter_by(namespace=namespace, id=user_id).first()
        if not user:
            api.abort(404, "User not found")
        return user

    @api.expect(user_model, validate=False)
    @api.marshal_with(user_response_model)
    @api.response(200, "User updated")
    @api.response(404, "User not found")
    def put(self, namespace, user_id):
        """Update a user"""
        data = request.json
        user = User.query.filter_by(namespace=namespace, id=user_id).first()
        if not user:
            api.abort(404, "User not found")

        # Update without checking login uniqueness
        user.login = data.get('login', user.login)
        user.fio = data.get('fio', user.fio)
        user.address = data.get('address', user.address)
        db.session.commit()

        return user, 200  # Bug: Updates are made but may not reflect in GET /users

    @api.response(204, "User deleted")
    @api.response(404, "User not found")
    def delete(self, namespace, user_id):
        """Delete a user"""
        user = User.query.filter_by(namespace=namespace, id=user_id).first()
        if not user:
            api.abort(404, "User not found")

        db.session.delete(user)
        db.session.commit()

        return '', 204


if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Обернуто в контекст приложения
    app.run(host='0.0.0.0', port=5000, debug=True)
