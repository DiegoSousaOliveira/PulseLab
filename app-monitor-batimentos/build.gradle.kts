// Arquivo de build do projeto (raiz). Os módulos ficam em settings.gradle.kts.
// O Android Gradle Plugin 9 já traz o Kotlin embutido; o plugin "compose"
// ativa o compilador do Jetpack Compose.
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.compose) apply false
}
