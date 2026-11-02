// Application build for the pinned upstream source. Publishing plugins and
// upstream tests are not part of the runtime artifact build.
scalaVersion := "2.12.16"
name := "adrs-pdffigures2"
version := "0.1.0-adrs1"
libraryDependencies ++= Seq(
  "io.spray" %% "spray-json" % "1.3.6",
  "com.github.scopt" %% "scopt" % "4.1.0",
  "ch.qos.logback" % "logback-classic" % "1.2.13",
  "org.slf4j" % "jcl-over-slf4j" % "1.7.36",
  "org.apache.pdfbox" % "pdfbox" % "2.0.37",
  "org.apache.pdfbox" % "fontbox" % "2.0.37",
  "com.typesafe" % "config" % "1.4.2",
  "org.bouncycastle" % "bcprov-jdk18on" % "1.86",
  "org.bouncycastle" % "bcmail-jdk18on" % "1.86",
  "org.bouncycastle" % "bcpkix-jdk18on" % "1.86"
)
assembly / mainClass := Some("org.allenai.pdffigures2.FigureExtractorBatchCli")
assembly / assemblyOutputPath := file("pdffigures2.jar")
assembly / test := {}
assembly / assemblyMergeStrategy := {
  case x if x.endsWith("module-info.class") => MergeStrategy.discard
  case PathList("org", "apache", "commons", xs @ _*) => MergeStrategy.first
  case x => (assembly / assemblyMergeStrategy).value(x)
}
