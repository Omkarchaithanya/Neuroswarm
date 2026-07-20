{{/*
Expand chart name and labels.
*/}}
{{- define "neuroswarm-arm.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "neuroswarm-arm.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "neuroswarm-arm.labels" -}}
app.kubernetes.io/name: {{ include "neuroswarm-arm.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}

{{- define "neuroswarm-arm.selectorLabels" -}}
app: neuroswarm-arm
app.kubernetes.io/name: {{ include "neuroswarm-arm.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "neuroswarm-arm.modelsVolume" -}}
{{- if .Values.models.hostPath }}
- name: models
  hostPath:
    path: {{ .Values.models.hostPath | quote }}
    type: DirectoryOrCreate
{{- else }}
- name: models
  persistentVolumeClaim:
    claimName: {{ include "neuroswarm-arm.fullname" . }}-models
{{- end }}
{{- end -}}

{{- define "neuroswarm-arm.modelsVolumeMount" -}}
- name: models
  mountPath: {{ .Values.models.mountPath }}
  readOnly: true
{{- end -}}

{{- define "neuroswarm-arm.extraVolumes" -}}
{{- if .Values.okf.hostPath }}
- name: okf
  hostPath:
    path: {{ .Values.okf.hostPath | quote }}
    type: DirectoryOrCreate
{{- end }}
{{- if .Values.work.hostPath }}
- name: work
  hostPath:
    path: {{ .Values.work.hostPath | quote }}
    type: DirectoryOrCreate
{{- end }}
{{- end -}}

{{- define "neuroswarm-arm.extraVolumeMounts" -}}
{{- if .Values.okf.hostPath }}
- name: okf
  mountPath: {{ .Values.okf.mountPath }}
  readOnly: true
{{- end }}
{{- if .Values.work.hostPath }}
- name: work
  mountPath: {{ .Values.work.mountPath }}
{{- end }}
{{- end -}}
