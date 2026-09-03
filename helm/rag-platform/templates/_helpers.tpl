{{- define "rag-platform.fullname" -}}{{ .Release.Name }}{{- end }}
{{- define "rag-platform.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "rag-platform.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end }}
{{- define "rag-platform.image" -}}
{{- $image := index .Values.images .image -}}
{{- printf "%s@%s" $image.repository (required (printf "images.%s.digest is required; tags are forbidden" .image) $image.digest) -}}
{{- end }}

