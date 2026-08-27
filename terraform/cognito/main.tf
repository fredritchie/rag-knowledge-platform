resource "aws_cognito_user_pool" "this" {
  name                = "${var.name}-users"
  deletion_protection = var.deletion_protection

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  username_configuration {
    case_sensitive = false
  }

  password_policy {
    minimum_length                   = 14
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 7
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  schema {
    attribute_data_type      = "String"
    developer_only_attribute = false
    mutable                  = true
    name                     = "tenant_id"
    required                 = false

    string_attribute_constraints {
      min_length = 1
      max_length = 64
    }
  }

  schema {
    attribute_data_type      = "String"
    developer_only_attribute = false
    mutable                  = true
    name                     = "groups"
    required                 = false

    string_attribute_constraints {
      min_length = 1
      max_length = 2048
    }
  }
}

resource "aws_cognito_user_pool_domain" "this" {
  domain       = var.name
  user_pool_id = aws_cognito_user_pool.this.id
}

resource "aws_cognito_user_pool_client" "web" {
  name         = "${var.name}-web"
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret               = false
  prevent_user_existence_errors = "ENABLED"

  allowed_oauth_flows                  = ["code"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  callback_urls                        = var.callback_urls
  logout_urls                          = var.logout_urls
  supported_identity_providers         = ["COGNITO"]

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 1

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  explicit_auth_flows = [
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH",
  ]

  read_attributes = [
    "email",
    "email_verified",
    "custom:tenant_id",
    "custom:groups",
  ]
}

resource "aws_cognito_user_group" "roles" {
  for_each = toset(["ADMIN", "EDITOR", "VIEWER"])

  name         = each.value
  user_pool_id = aws_cognito_user_pool.this.id
  description  = "Phase 7 ${lower(each.value)} test group."
}

resource "aws_cognito_user" "test" {
  for_each = var.test_users

  user_pool_id             = aws_cognito_user_pool.this.id
  username                 = each.value.email
  desired_delivery_mediums = ["EMAIL"]

  attributes = {
    email              = each.value.email
    email_verified     = "true"
    "custom:tenant_id" = each.value.tenant_id
    "custom:groups"    = join(",", each.value.groups)
  }
}

resource "aws_cognito_user_in_group" "test" {
  for_each = {
    for membership in flatten([
      for username, user in var.test_users : [
        for group in user.groups : {
          key      = "${username}:${group}"
          username = user.email
          group    = group
        }
      ]
    ]) : membership.key => membership
  }

  user_pool_id = aws_cognito_user_pool.this.id
  username     = aws_cognito_user.test[split(":", each.key)[0]].username
  group_name   = aws_cognito_user_group.roles[each.value.group].name
}
