<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output method="text" encoding="UTF-8"/>

  <xsl:template match="/result">
    <xsl:text>{"products":[</xsl:text>
    <xsl:for-each select="items/item">
      <xsl:if test="position() &gt; 1">,</xsl:if>
      <xsl:variable name="journal" select="(.//partOf[title])[1]"/>
      <xsl:text>{"local_identifier":"</xsl:text>
      <xsl:value-of select="@href"/>
      <xsl:text>","entity_type":"product","title":"</xsl:text>
      <xsl:call-template name="esc"><xsl:with-param name="s" select="title"/></xsl:call-template>
      <xsl:text>","contributors":[</xsl:text>
      <xsl:for-each select="contributorship/item/agent[familyName or givenName]">
        <xsl:if test="position() &gt; 1">,</xsl:if>
        <xsl:text>{"given_name":"</xsl:text>
        <xsl:call-template name="esc"><xsl:with-param name="s" select="givenName"/></xsl:call-template>
        <xsl:text>","family_name":"</xsl:text>
        <xsl:call-template name="esc"><xsl:with-param name="s" select="familyName"/></xsl:call-template>
        <xsl:text>"}</xsl:text>
      </xsl:for-each>
      <xsl:text>],"venue":{"name":"</xsl:text>
      <xsl:call-template name="esc"><xsl:with-param name="s" select="$journal/title"/></xsl:call-template>
      <xsl:text>","issn":[</xsl:text>
      <xsl:for-each select="$journal/identifier/item/value[contains(., '-')]">
        <xsl:if test="position() &gt; 1">,</xsl:if>
        <xsl:text>"</xsl:text>
        <xsl:call-template name="esc"><xsl:with-param name="s" select="."/></xsl:call-template>
        <xsl:text>"</xsl:text>
      </xsl:for-each>
      <xsl:text>]}}</xsl:text>
    </xsl:for-each>
    <xsl:text>]}</xsl:text>
  </xsl:template>

  <xsl:template name="esc">
    <xsl:param name="s"/>
    <xsl:variable name="bs">
      <xsl:call-template name="replace">
        <xsl:with-param name="text" select="$s"/>
        <xsl:with-param name="from" select="'\'"/>
        <xsl:with-param name="to" select="'\\'"/>
      </xsl:call-template>
    </xsl:variable>
    <xsl:call-template name="replace">
      <xsl:with-param name="text" select="$bs"/>
      <xsl:with-param name="from" select="'&quot;'"/>
      <xsl:with-param name="to" select="'\&quot;'"/>
    </xsl:call-template>
  </xsl:template>

  <xsl:template name="replace">
    <xsl:param name="text"/>
    <xsl:param name="from"/>
    <xsl:param name="to"/>
    <xsl:choose>
      <xsl:when test="contains($text, $from)">
        <xsl:value-of select="substring-before($text, $from)"/>
        <xsl:value-of select="$to"/>
        <xsl:call-template name="replace">
          <xsl:with-param name="text" select="substring-after($text, $from)"/>
          <xsl:with-param name="from" select="$from"/>
          <xsl:with-param name="to" select="$to"/>
        </xsl:call-template>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="$text"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>
</xsl:stylesheet>
