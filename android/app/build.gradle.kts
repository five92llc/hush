import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// The version comes from the command line (-PversionName=1.2.3), so a release build and its tag always agree.
val versionNameArg = (project.findProperty("versionName") as String?) ?: "1.0.0"
val parts = versionNameArg.split(".").map { it.toIntOrNull() ?: 0 } + listOf(0, 0, 0)
val versionCodeArg = parts[0] * 10000 + parts[1] * 100 + parts[2]

// Release signing. Every update must be signed with the same key, or Android refuses to install it over the old one.
val keystoreProps = Properties().apply {
    val f = rootProject.file("keystore/keystore.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}
fun secret(name: String, prop: String): String? = System.getenv(name) ?: keystoreProps.getProperty(prop)

android {
    namespace = "com.hush.tv"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.hush.tv"
        minSdk = 22              // Fire TV Stick (2nd gen) runs Android 5.1
        targetSdk = 34
        versionCode = versionCodeArg
        versionName = versionNameArg
    }

    signingConfigs {
        create("release") {
            val path = secret("HUSH_KEYSTORE_PATH", "storeFile") ?: rootProject.file("keystore/hush-release.jks").path
            if (rootProject.file(path).exists()) {
                storeFile = rootProject.file(path)
                storePassword = secret("HUSH_KEYSTORE_PASSWORD", "storePassword")
                keyAlias = secret("HUSH_KEY_ALIAS", "keyAlias")
                keyPassword = secret("HUSH_KEY_PASSWORD", "keyPassword")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release").takeIf { it.storeFile != null } ?: signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { buildConfig = true }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
}
