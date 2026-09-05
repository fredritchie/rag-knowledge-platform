output "project_name" { value = aws_codebuild_project.deploy.name }
output "trigger_role_arn" { value = aws_iam_role.trigger.arn }
output "codebuild_role_arn" { value = aws_iam_role.codebuild.arn }
